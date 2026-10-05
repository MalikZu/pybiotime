"""An in-memory BioTime server for tests.

`FakeBioTime` answers like a BioTime 9.5 server, including its quirks: next links that
point at an internal host, sort orders it ignores, HTML pages for unknown paths and
400 for rejected logins. Pass `version="8.0"`, `"8.5"` or `"9.0"` to imitate an older
server: employees, the API docs page and the resign API change to match.
`after_request` lets a test change the data between requests, as new punches do on a
live server. Plug it into either client:

    fake = FakeBioTime(username="api", password="secret")
    fake.add_terminal(sn="TEST0000001", alias="Main gate")
    fake.add_transaction(emp_code="1001", punch_time=datetime(2026, 10, 1, 8, 0))

    client = BioTimeClient("http://biotime.test", auth=TokenAuth("api", "secret"),
                           transport=fake.transport())
"""

from __future__ import annotations

import base64
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

import httpx

from pybiotime.testing._personnel import VERSIONS, PersonnelData

__all__ = ["VERSIONS", "FakeBioTime", "RecordedRequest"]

_FORMAT = "%Y-%m-%d %H:%M:%S"
_DOCS_TITLES = {
    "8.0": "BIOTIME API DOCS",
    "8.5": "BIOTIME API DOCS",
    "9.0": "ZKBio Time API DOCS",
    "9.5": "BioTime 9.5 API DOCS",
}
_NOT_FOUND_PAGE = (
    b"<!DOCTYPE HTML>\n<html>\n<head><title>Page not found</title></head>\n"
    b"<body><h1>Page not found</h1></body>\n</html>\n"
)


@dataclass(frozen=True)
class RecordedRequest:
    method: str
    host: str
    path: str
    params: dict[str, str]
    authorization: str | None
    json: Any = None


@dataclass
class FakeBioTime(PersonnelData):
    """In-memory BioTime server. All state is public so tests can inspect and change it."""

    username: str = "api"
    password: str = "secret"  # noqa: S105 - a fake server's default
    #: Address used in next links, to check clients do not follow the host.
    internal_base: str = "http://127.0.0.1:8081"
    default_page_size: int = 10
    #: Lifetime of the JSON Web Tokens it issues.
    jwt_lifetime: float = 3600.0
    #: Sort orders it honours for transactions; others are ignored, as on a real server.
    honoured_orders: set[str] = field(
        default_factory=lambda: {"punch_time", "-punch_time", "upload_time", "-upload_time"}
    )
    terminals: list[dict[str, Any]] = field(default_factory=list)
    transactions: list[dict[str, Any]] = field(default_factory=list)
    requests: list[RecordedRequest] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)
    #: Statuses to answer the next matching requests with, before any real handling.
    #: Each entry is ``(method, path_prefix, status)``; it is removed once used.
    failures: list[tuple[str, str, int]] = field(default_factory=list)
    #: Called with each request after it is answered. Use it to change the data between
    #: requests, for example to add punches while a client is paging.
    after_request: Callable[[RecordedRequest], None] | None = None
    _next_id: int = 1

    def __post_init__(self) -> None:
        if self.version not in VERSIONS:
            raise ValueError(f"version must be one of {', '.join(VERSIONS)}")

    def transport(self) -> httpx.MockTransport:
        """A transport for `BioTimeClient` or `AsyncBioTimeClient`."""
        return httpx.MockTransport(self.handle)

    # --- data -------------------------------------------------------------------------

    def add_terminal(self, *, sn: str, alias: str | None = None, **fields: Any) -> dict[str, Any]:
        terminal = {
            "id": self._new_id(),
            "sn": sn,
            "ip_address": "192.0.2.10",
            "alias": alias if alias is not None else sn,
            "terminal_name": None,
            "fw_ver": None,
            "push_ver": None,
            "state": "1",
            "terminal_tz": 0,
            "area": {"id": 1, "area_code": "1", "area_name": "Head office"},
            "last_activity": None,
            "transfer_time": "00:00;14:05",
            "transfer_interval": 1,
            "is_attendance": 1,
            "area_name": "Head office",
        }
        terminal.update(fields)
        self.terminals.append(terminal)
        return terminal

    def add_transaction(
        self,
        *,
        emp_code: str,
        punch_time: datetime,
        terminal_sn: str = "",
        punch_state: str = "0",
        upload_time: datetime | None = None,
        **fields: Any,
    ) -> dict[str, Any]:
        """Record a punch. `upload_time` defaults to `punch_time`."""
        transaction = {
            "id": self._new_id(),
            "emp": None,
            "emp_code": emp_code,
            "first_name": None,
            "last_name": None,
            "department": None,
            "position": None,
            "punch_time": punch_time.strftime(_FORMAT),
            "punch_state": punch_state,
            "punch_state_display": None,
            "verify_type": 0,
            "verify_type_display": "Any",
            "work_code": None,
            "gps_location": "",
            "area_alias": None,
            "terminal_sn": terminal_sn,
            "temperature": 0.0,
            "is_mask": "-",
            "terminal_alias": None,
            "upload_time": (upload_time or punch_time).strftime(_FORMAT),
            "longitude": None,
            "latitude": None,
        }
        transaction.update(fields)
        self.transactions.append(transaction)
        return transaction

    def fail_next(self, status: int, *, method: str = "GET", path: str = "/") -> None:
        """Answer the next request matching `method` and `path` prefix with `status`."""
        self.failures.append((method, path, status))

    def _new_id(self) -> int:
        value = self._next_id
        self._next_id += 1
        return value

    # --- HTTP -------------------------------------------------------------------------

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else None
        recorded = RecordedRequest(
            request.method,
            request.url.host,
            request.url.path,
            dict(request.url.params),
            request.headers.get("Authorization"),
            body,
        )
        self.requests.append(recorded)
        response = self._respond(recorded)
        if self.after_request is not None:
            self.after_request(recorded)
        return response

    def _respond(self, request: RecordedRequest) -> httpx.Response:
        path, params, authorization = request.path, request.params, request.authorization
        for index, (method, prefix, status) in enumerate(self.failures):
            if request.method == method and path.startswith(prefix):
                del self.failures[index]
                return httpx.Response(status, json={"detail": f"Injected HTTP {status}."})

        if path in ("/api-token-auth/", "/jwt-api-token-auth/"):
            return self._login(request.method, path, request.json)
        html = {"Content-Type": "text/html"}
        if path == "/api/docs/":
            title = _DOCS_TITLES[self.version].encode()
            page = b"<!DOCTYPE html><html><head><title>" + title + b"</title></head></html>"
            return httpx.Response(200, content=page, headers=html)
        unknown = not path.startswith(("/iclock/api/", "/personnel/api/")) or (
            path.startswith("/personnel/api/resigns/") and not self.has_resigns
        )
        if unknown:
            return httpx.Response(200, content=_NOT_FOUND_PAGE, headers=html)

        if not authorization:
            return _detail(401, "Authentication credentials were not provided.")
        scheme, _, token = authorization.partition(" ")
        if scheme not in ("Token", "JWT") or token not in self.tokens or _expired(token):
            return _detail(401, "Invalid token.")

        if path.startswith("/personnel/api/"):
            answer = self._personnel(request.method, path, params, request.json)
            if answer is not None:
                return answer
        if path == "/iclock/api/terminals/":
            return self._list(path, params, self._filter_terminals(params))
        if path == "/iclock/api/transactions/":
            return self._transactions(path, params)
        for prefix, rows in (
            ("/iclock/api/terminals/", self.terminals),
            ("/iclock/api/transactions/", self.transactions),
        ):
            if path.startswith(prefix):
                return _detail_object(rows, path[len(prefix) :].strip("/"))
        return _detail(404, "Not found.")

    def _login(self, method: str, path: str, body: Any) -> httpx.Response:
        if method != "POST":
            return _detail(405, f'Method "{method}" not allowed.')
        if (
            not isinstance(body, dict)
            or body.get("username") != self.username
            or body.get("password") != self.password
        ):
            return httpx.Response(
                400, json={"non_field_errors": ["Unable to log in with provided credentials."]}
            )
        if "jwt" in path:
            token = _make_jwt(time.time() + self.jwt_lifetime)
        else:
            token = secrets.token_hex(20)
        self.tokens.add(token)
        return httpx.Response(200, json={"token": token})

    def _filter_terminals(self, params: dict[str, str]) -> list[dict[str, Any]]:
        rows = self.terminals
        for key in ("sn", "alias"):
            if key in params:
                rows = [r for r in rows if params[key].lower() in str(r[key]).lower()]
        return rows

    def _transactions(self, path: str, params: dict[str, str]) -> httpx.Response:
        rows = list(self.transactions)
        try:
            for key, keep in (("start_time", "ge"), ("end_time", "le")):
                if key in params:
                    bound = datetime.strptime(params[key], _FORMAT)
                    rows = [r for r in rows if _compare(r["punch_time"], bound, keep)]
        except ValueError:
            return httpx.Response(400, json={"start_time": ["Enter a valid date/time."]})
        for key in ("emp_code", "terminal_sn"):
            if key in params:
                rows = [r for r in rows if r[key] == params[key]]

        rows.sort(key=lambda r: r["id"])
        order = params.get("ordering")
        if order in self.honoured_orders:
            field_name = order.lstrip("-")
            # Ties fall back to id order, reversed for descending sorts, as the real server does.
            rows.sort(key=lambda r: (r[field_name], r["id"]), reverse=order.startswith("-"))
        return self._list(path, params, rows)

    def _list(
        self, path: str, params: dict[str, str], rows: list[dict[str, Any]]
    ) -> httpx.Response:
        try:
            page = max(1, int(params.get("page", "1")))
            size = max(1, int(params.get("page_size", str(self.default_page_size))))
        except ValueError:
            return _detail(404, "Invalid page.")
        start = (page - 1) * size
        if start and start >= len(rows):
            return _detail(404, "Invalid page.")
        chunk = rows[start : start + size]

        def link(number: int) -> str:
            query = {**params, "page": str(number)}
            if number == 1:
                del query["page"]
            return f"{self.internal_base}{path}?{urlencode(query)}"

        return httpx.Response(
            200,
            json={
                "count": len(rows),
                "next": link(page + 1) if start + size < len(rows) else None,
                "previous": link(page - 1) if page > 1 else None,
                "msg": "",
                "code": 0,
                "data": chunk,
            },
        )


def _detail(status: int, message: str) -> httpx.Response:
    return httpx.Response(status, json={"detail": message})


def _detail_object(rows: list[dict[str, Any]], key: str) -> httpx.Response:
    for row in rows:
        if str(row["id"]) == key:
            return httpx.Response(200, json=row)
    return _detail(404, "Not found.")


def _compare(value: str, bound: datetime, keep: str) -> bool:
    parsed = datetime.strptime(value, _FORMAT)
    return parsed >= bound if keep == "ge" else parsed <= bound


def _make_jwt(exp: float) -> str:
    def part(data: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    header = part({"alg": "HS256", "typ": "JWT"})
    payload = part({"exp": int(exp), "nonce": secrets.token_hex(4)})
    return f"{header}.{payload}.fake-signature"


def _expired(token: str) -> bool:
    if token.count(".") != 2:
        return False
    payload = token.split(".")[1]
    claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    return bool(claims["exp"] < time.time())
