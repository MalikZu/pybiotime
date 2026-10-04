# Generated from tests/_async/test_client.py by scripts/unasync.py. Do not edit.

from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest

from pybiotime import (
    AuthenticationError,
    BasicAuth,
    BioTimeClient,
    FaultPageError,
    JWTAuth,
    LoginSuspendedError,
    NotFoundError,
    ServerError,
    TokenAuth,
    TransportError,
)
from pybiotime.testing import FakeBioTime

BASE = "http://biotime.test"


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("pybiotime._sync.client._backoff", lambda attempt: 0.0)


@pytest.fixture
def fake() -> FakeBioTime:
    server = FakeBioTime(username="api", password="secret")
    server.add_terminal(sn="TEST0000001", alias="Main gate")
    server.add_terminal(sn="TEST0000001-B", alias="Back door")
    for minute in range(25):
        server.add_transaction(
            emp_code=f"{1000 + minute % 3}",
            punch_time=datetime(2026, 10, 1, 8, minute),
            terminal_sn="TEST0000001",
        )
    return server


def client_for(fake: FakeBioTime, **kwargs: object) -> BioTimeClient:
    options: dict[str, object] = {"auth": TokenAuth("api", "secret"), "page_size": 10}
    options.update(kwargs)
    return BioTimeClient(BASE, transport=fake.transport(), **options)  # type: ignore[arg-type]


def logins(fake: FakeBioTime) -> int:
    return sum(1 for r in fake.requests if r.path.endswith("-token-auth/"))


class TestAuthentication:
    def test_logs_in_once_and_reuses_the_token(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            client.terminals.list().first()
            client.terminals.list().first()
        assert logins(fake) == 1
        data_requests = [r for r in fake.requests if r.path.startswith("/iclock/")]
        assert all(r.authorization and r.authorization.startswith("Token ") for r in data_requests)

    def test_logs_in_again_when_the_token_is_rejected(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            client.terminals.list().first()
            fake.tokens.clear()
            terminal = client.terminals.list().first()
        assert terminal is not None
        assert logins(fake) == 2

    def test_static_token(self, fake: FakeBioTime) -> None:
        fake.tokens.add("known-token")
        with client_for(fake, auth=TokenAuth(token="known-token")) as client:
            assert client.terminals.list().count() == 2
            fake.tokens.clear()
            with pytest.raises(AuthenticationError):
                client.terminals.list().count()
        assert logins(fake) == 0

    def test_rejected_credentials_suspend_logins(self, fake: FakeBioTime) -> None:
        with client_for(fake, auth=TokenAuth("api", "wrong")) as client:
            with pytest.raises(AuthenticationError, match="rejected the login") as caught:
                client.terminals.list().first()
            assert caught.value.status_code == 400
            with pytest.raises(LoginSuspendedError) as suspended:
                client.terminals.list().first()
        assert suspended.value.retry_after > 0
        assert logins(fake) == 1

    def test_jwt(self, fake: FakeBioTime) -> None:
        with client_for(fake, auth=JWTAuth("api", "secret")) as client:
            client.terminals.list().first()
            client.terminals.list().first()
        assert logins(fake) == 1
        assert fake.requests[-1].authorization is not None
        assert fake.requests[-1].authorization.startswith("JWT ")

    def test_jwt_close_to_expiry_logs_in_again(self, fake: FakeBioTime) -> None:
        fake.jwt_lifetime = 30
        with client_for(fake, auth=JWTAuth("api", "secret", refresh_margin=60)) as client:
            client.terminals.list().first()
            client.terminals.list().first()
        assert logins(fake) == 2

    def test_basic_auth_never_logs_in(self) -> None:
        seen: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request.headers.get("Authorization"))
            return httpx.Response(200, json={"count": 0, "next": None, "data": []})

        auth = BasicAuth("api", "secret")
        transport = httpx.MockTransport(handler)
        with BioTimeClient(BASE, auth=auth, transport=transport) as client:
            client.terminals.list().first()
        assert seen == [auth.authorization()]


class TestPagination:
    def test_iterates_every_page_via_query_string_only(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            punches = [p for p in client.transactions.list()]
        assert [p.id for p in punches] == [t["id"] for t in fake.transactions]
        pages = [r for r in fake.requests if r.path == "/iclock/api/transactions/"]
        assert len(pages) == 3
        # The fake's next links point at 127.0.0.1; the client must stay on its own host.
        assert {r.host for r in pages} == {"biotime.test"}

    def test_pages(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            pages = [page for page in client.transactions.list(page_size=20).pages()]
        assert [len(p.items) for p in pages] == [20, 5]
        assert [p.has_next for p in pages] == [True, False]
        assert pages[0].count == 25

    def test_first_and_count_fetch_one_object(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            first = client.transactions.list(order_by="-punch_time").first()
            count = client.transactions.list(emp_code="1000").count()
        assert first is not None
        assert first.punch_time == datetime(2026, 10, 1, 8, 24)
        assert count == 9
        assert {r.params.get("page_size") for r in fake.requests if r.method == "GET"} == {"1"}


class TestTransactions:
    def test_filters(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            punches = [
                p
                for p in client.transactions.list(
                    start=datetime(2026, 10, 1, 8, 10),
                    end=datetime(2026, 10, 1, 8, 12),
                    terminal_sn="TEST0000001",
                )
            ]
        assert [p.punch_time.minute for p in punches] == [10, 11, 12]
        sent = fake.requests[-1].params
        assert sent["start_time"] == "2026-10-01 08:10:00"
        assert sent["end_time"] == "2026-10-01 08:12:00"

    def test_timezone(self, fake: FakeBioTime) -> None:
        dubai = ZoneInfo("Asia/Dubai")
        with client_for(fake, timezone="Asia/Dubai") as client:
            start = datetime(2026, 10, 1, 4, 20, tzinfo=ZoneInfo("UTC"))
            punch = client.transactions.list(start=start).first()
        assert punch is not None
        assert punch.punch_time == datetime(2026, 10, 1, 8, 20, tzinfo=dubai)
        assert fake.requests[-1].params["start_time"] == "2026-10-01 08:20:00"

    def test_get(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            punch = client.transactions.get(fake.transactions[0]["id"])
            assert punch.emp_code == "1000"
            with pytest.raises(NotFoundError):
                client.transactions.get(999999)


class TestTerminals:
    def test_get_by_sn_matches_exactly(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            terminal = client.terminals.get_by_sn("TEST0000001")
            missing = client.terminals.get_by_sn("TEST")
        assert terminal is not None
        assert terminal.alias == "Main gate"
        assert missing is None

    def test_get(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            terminal = client.terminals.get(fake.terminals[1]["id"])
        assert terminal.sn == "TEST0000001-B"


class TestErrorsAndRetries:
    def test_get_is_retried_on_503(self, fake: FakeBioTime) -> None:
        fake.fail_next(503, path="/iclock/")
        with client_for(fake) as client:
            assert client.terminals.list().count() == 2

    def test_gives_up_after_the_retries(self, fake: FakeBioTime) -> None:
        for _ in range(3):
            fake.fail_next(503, path="/iclock/")
        with client_for(fake, retries=2) as client:
            with pytest.raises(ServerError):
                client.terminals.list().count()

    def test_post_is_never_retried(self, fake: FakeBioTime) -> None:
        fake.fail_next(503, method="POST", path="/personnel/")
        with client_for(fake) as client:
            with pytest.raises(ServerError):
                client.request("POST", "/personnel/api/departments/", json={})
        posts = [r for r in fake.requests if r.path == "/personnel/api/departments/"]
        assert len(posts) == 1

    def test_network_errors(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            raise httpx.ConnectError("connection refused", request=request)

        auth = TokenAuth(token="x")
        transport = httpx.MockTransport(handler)
        with BioTimeClient(BASE, auth=auth, transport=transport, retries=1) as client:
            with pytest.raises(TransportError):
                client.terminals.list().first()
        assert calls == 2

    def test_html_page_is_a_fault(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            with pytest.raises(FaultPageError):
                client.request("GET", "/base/api/nothing-here/")

    def test_escape_hatch_returns_json(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            body = client.request("get", "/iclock/api/terminals/", params={"page_size": 1})
        assert body["count"] == 2
        assert len(body["data"]) == 1


def test_repr_hides_secrets(fake: FakeBioTime) -> None:
    client = client_for(fake, auth=TokenAuth("api", "hunter2"))
    assert "hunter2" not in repr(client)
    assert "biotime.test" in repr(client)
