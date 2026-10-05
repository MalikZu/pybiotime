# Generated from src/pybiotime/_async/client.py by scripts/unasync.py. Do not edit.

from __future__ import annotations

import logging
import random
import ssl
import time
from datetime import tzinfo
from types import TracebackType
from typing import Any

import httpx

from pybiotime._concurrency import Lock, sleep
from pybiotime._core import decode_response, parse_page, resolve_timezone
from pybiotime._sync.personnel import (
    Areas,
    Departments,
    Employees,
    Positions,
    Resigns,
)
from pybiotime._sync.resources import Terminals, Transactions
from pybiotime._version import __version__
from pybiotime.auth import Auth
from pybiotime.compat import ServerInfo, docs_title, employee_shape, guess_version
from pybiotime.errors import (
    APIError,
    AuthenticationError,
    FaultPageError,
    LoginSuspendedError,
    NotFoundError,
    TransportError,
)

__all__ = ["BioTimeClient"]

logger = logging.getLogger("pybiotime")

_RETRY_STATUSES = frozenset({502, 503, 504})


class BioTimeClient:
    """Client for one BioTime server.

    Args:
        base_url: Server address with scheme and port, for example ``"http://10.0.0.5:8090"``.
        auth: How to authenticate, for example ``TokenAuth("api_user", "secret")``.
        timezone: The server's timezone, as a name such as ``"Asia/Dubai"`` or a `tzinfo`.
            BioTime timestamps carry no timezone. When this is set, returned timestamps get
            it attached and aware datetimes in filters are converted to it.
        timeout: Seconds to wait for each response. The first request after the server
            has been idle can be slow, hence the generous default.
        verify: TLS certificate check. ``False`` accepts the self-signed certificate many
            BioTime servers use; a path or `ssl.SSLContext` trusts a specific CA.
        page_size: Objects per page when listing.
        retries: How often to retry a GET after a network error or HTTP 502, 503 or 504.
            Other methods are never retried.
        login_cooldown: Seconds to wait before logging in again after the server rejected
            the credentials, so a wrong password does not lock the account.
        transport: An httpx transport, for testing. See `pybiotime.testing`.

    Use it as a context manager, or call `close()` when done.
    """

    def __init__(
        self,
        base_url: str,
        *,
        auth: Auth,
        timezone: str | tzinfo | None = None,
        timeout: float = 60.0,
        verify: bool | str | ssl.SSLContext = True,
        page_size: int = 100,
        retries: int = 2,
        login_cooldown: float = 60.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be at least 1")
        self.auth = auth
        self.timezone = resolve_timezone(timezone)
        self.page_size = page_size
        self.retries = retries
        self.login_cooldown = login_cooldown
        if isinstance(verify, str):
            # httpx deprecates a CA path here; it wants an SSL context.
            verify = ssl.create_default_context(cafile=verify)
        self._login_lock = Lock()
        self._http = httpx.Client(
            base_url=base_url,
            timeout=timeout,
            verify=verify,
            transport=transport,
            follow_redirects=False,
            headers={
                "Accept": "application/json",
                # Display fields such as punch_state_display follow this language.
                "Accept-Language": "en",
                "User-Agent": f"pybiotime/{__version__}",
            },
        )
        self.terminals = Terminals(self)
        self.transactions = Transactions(self)
        self.departments = Departments(self)
        self.areas = Areas(self)
        self.positions = Positions(self)
        self.employees = Employees(self)
        self.resigns = Resigns(self)

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        """Call any endpoint and return the decoded JSON.

        Use this for endpoints pybiotime does not wrap yet. Authentication, retries and
        error handling work as for every other call.
        """
        return self._request(method.upper(), path, params=params, json=json)

    def server_info(self) -> ServerInfo:
        """Find out which BioTime version this is, and whether it has the resign API.

        No endpoint reports the version, so this reads three signals: the title of the
        public ``/api/docs/`` page, how one employee's attendance flags are shaped, and
        whether the resign endpoint answers. It makes three small requests.
        """
        title = None
        page = self._send("GET", "/api/docs/", auth=None)
        if page.status_code == 200:
            title = docs_title(page.text)

        body = self._request("GET", self.employees.path, params={"page_size": "1"})
        items = parse_page(body, method="GET", path=self.employees.path).items
        shape = employee_shape(items[0]) if items else None

        try:
            self._request("GET", self.resigns.path, params={"page_size": "1"})
            has_resigns = True
        except (FaultPageError, NotFoundError):
            has_resigns = False

        return ServerInfo(
            version=guess_version(title, shape, has_resigns),
            docs_title=title,
            employee_shape=shape,
            has_resigns=has_resigns,
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
    ) -> Any:
        authorization = self._authorization()
        response = self._send(method, path, params=params, json=json, auth=authorization)
        if response.status_code == 401 and self.auth.can_login:
            authorization = self._authorization(rejected=authorization)
            response = self._send(method, path, params=params, json=json, auth=authorization)
        return decode_response(
            response.status_code,
            response.headers.get("content-type", ""),
            response.content,
            method=method,
            path=path,
        )

    def _authorization(self, rejected: str | None = None) -> str | None:
        if self.auth.needs_login(rejected):
            with self._login_lock:
                if self.auth.needs_login(rejected):
                    self._login()
        return self.auth.authorization()

    def _login(self) -> None:
        path = self.auth.login_path
        if path is None:
            return
        wait = self.auth.suspended_for()
        if wait:
            raise LoginSuspendedError(
                f"Not logging in for another {wait:.0f}s: the server rejected these "
                "credentials and retrying could lock the account",
                retry_after=wait,
                path=path,
            )
        response = self._send("POST", path, json=self.auth.login_body(), auth=None)
        try:
            body = decode_response(
                response.status_code,
                response.headers.get("content-type", ""),
                response.content,
                method="POST",
                path=path,
            )
        except APIError as exc:
            # Bad credentials come back as 400, not 401.
            if exc.status_code in (400, 401, 403):
                self.auth.suspend(self.login_cooldown)
                raise AuthenticationError(
                    f"BioTime rejected the login: {exc.detail or f'HTTP {exc.status_code}'}",
                    status_code=exc.status_code,
                    method="POST",
                    path=path,
                    detail=exc.detail,
                    body=exc.body,
                ) from None
            raise
        self.auth.accept_login(body)
        logger.debug("logged in via %s", path)

    def _send(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        auth: str | None,
    ) -> httpx.Response:
        headers = {"Authorization": auth} if auth else None
        attempt = 0
        while True:
            started = time.monotonic()
            try:
                response = self._http.request(
                    method, path, params=params, json=json, headers=headers
                )
            except httpx.TransportError as exc:
                if method == "GET" and attempt < self.retries:
                    attempt += 1
                    logger.debug("%s %s failed (%s), retry %d", method, path, exc, attempt)
                    sleep(_backoff(attempt))
                    continue
                raise TransportError(f"{method} {path} failed: {exc!r}") from exc

            elapsed = time.monotonic() - started
            logger.debug("%s %s -> %d in %.2fs", method, path, response.status_code, elapsed)
            if (
                method == "GET"
                and response.status_code in _RETRY_STATUSES
                and attempt < self.retries
            ):
                attempt += 1
                sleep(_backoff(attempt))
                continue
            return response

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> BioTimeClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"{type(self).__name__}({str(self._http.base_url)!r}, auth={self.auth!r})"


def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter: about 0.5 s, 1 s, 2 s, ..., capped at 10 s."""
    return min(10.0, 0.5 * 2.0 ** (attempt - 1)) * (0.5 + random.random())  # noqa: S311
