# Generated from tests/_async/test_secrets_in_tracebacks.py by scripts/unasync.py. Do not edit.

"""Failed requests must not leave credentials in traceback locals.

Error reporters such as Frappe's log every frame's local variables with repr(). These
tests make requests fail in each way the client can fail, then look at every local of
every frame in the exception chain, and at the traceback formatted with its locals.
"""

import base64
import traceback
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pybiotime import BasicAuth, BioTimeClient, BioTimeError, JWTAuth, TokenAuth
from pybiotime.auth import Auth
from pybiotime.testing import FakeBioTime

PASSWORD = "hunter2-very-secret"
KNOWN_TOKEN = "f00dfeedf00dfeedf00dfeedf00dfeedf00dfeed"
BASIC = base64.b64encode(f"api:{PASSWORD}".encode()).decode()

AUTHS: dict[str, Callable[[], Auth]] = {
    "token login": lambda: TokenAuth("api", PASSWORD),
    "jwt login": lambda: JWTAuth("api", PASSWORD),
    "known token": lambda: TokenAuth(token=KNOWN_TOKEN),
    "basic": lambda: BasicAuth("api", PASSWORD),
}


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pybiotime._sync.client._backoff", lambda attempt: 0.0)


def frame_texts(error: BaseException) -> str:
    texts = [
        "".join(traceback.TracebackException.from_exception(error, capture_locals=True).format())
    ]
    seen: set[int] = set()
    pending: list[BaseException | None] = [error]
    while pending:
        current = pending.pop()
        if current is None or id(current) in seen:
            continue
        seen.add(id(current))
        tb = current.__traceback__
        while tb is not None:
            for name, value in tb.tb_frame.f_locals.items():
                texts.append(f"{name}={value!r}")
            tb = tb.tb_next
        pending += [current.__cause__, current.__context__]
    return "\n".join(texts)


def failure(client: BioTimeClient, call: Callable[[BioTimeClient], Any]) -> BioTimeError:
    try:
        call(client)
    except BioTimeError as error:
        return error
    raise AssertionError("the call did not fail")


def secrets_of(fake: FakeBioTime) -> list[str]:
    return [PASSWORD, KNOWN_TOKEN, BASIC, *fake.tokens]


def server(*, refuse: str | None = None) -> tuple[FakeBioTime, httpx.MockTransport]:
    """A fake that accepts the credentials above. `refuse` makes one path fail to connect."""
    fake = FakeBioTime(username="api", password=PASSWORD)
    fake.tokens.add(KNOWN_TOKEN)

    def handle(request: httpx.Request) -> httpx.Response:
        if refuse and request.url.path.startswith(refuse):
            raise httpx.ConnectError("connection refused", request=request)
        if request.headers.get("Authorization") == f"Basic {BASIC}":
            # The fake knows tokens only; let Basic through as the known token.
            request.headers["Authorization"] = f"Token {KNOWN_TOKEN}"
        return fake.handle(request)

    return fake, httpx.MockTransport(handle)


def client_for(auth: Auth, transport: httpx.MockTransport) -> BioTimeClient:
    return BioTimeClient("http://biotime.test", auth=auth, transport=transport, retries=1)


@pytest.mark.parametrize("kind", AUTHS)
def test_network_error_after_retries(kind: str) -> None:
    fake, transport = server(refuse="/iclock/")
    with client_for(AUTHS[kind](), transport) as client:
        error = failure(client, lambda c: c.terminals.list().first())
    text = frame_texts(error)
    assert "connection refused" in text
    for secret in secrets_of(fake):
        assert secret not in text


@pytest.mark.parametrize("kind", AUTHS)
def test_api_error(kind: str) -> None:
    fake, transport = server()
    with client_for(AUTHS[kind](), transport) as client:
        error = failure(client, lambda c: c.transactions.get(999999))
    text = frame_texts(error)
    assert "Not found" in text
    for secret in secrets_of(fake):
        assert secret not in text


@pytest.mark.parametrize("kind", ["token login", "jwt login"])
def test_rejected_login(kind: str) -> None:
    fake, transport = server()
    fake.password = "something-else"
    with client_for(AUTHS[kind](), transport) as client:
        error = failure(client, lambda c: c.terminals.list().first())
    text = frame_texts(error)
    assert "rejected the login" in text
    for secret in secrets_of(fake):
        assert secret not in text


@pytest.mark.parametrize("kind", ["token login", "jwt login"])
def test_network_error_while_logging_in(kind: str) -> None:
    fake, transport = server(refuse="/api-token-auth/")
    if kind == "jwt login":
        fake, transport = server(refuse="/jwt-api-token-auth/")
    with client_for(AUTHS[kind](), transport) as client:
        error = failure(client, lambda c: c.terminals.list().first())
    text = frame_texts(error)
    for secret in secrets_of(fake):
        assert secret not in text


def test_employee_secrets_in_a_failed_write() -> None:
    _, transport = server()
    with client_for(AUTHS["token login"](), transport) as client:
        error = failure(
            client,
            lambda c: c.employees.create(
                "1001",
                department_id=999,
                area_ids=[999],
                card_no="99887766",
                device_password="4321",
            ),
        )
    text = frame_texts(error)
    assert "99887766" not in text
    assert "'4321'" not in text
