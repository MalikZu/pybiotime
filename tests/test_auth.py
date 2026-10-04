import base64
import json
import time

import pytest

from pybiotime.auth import BasicAuth, JWTAuth, StaffJWTAuth, StaffTokenAuth, TokenAuth


def make_jwt(exp: float) -> str:
    def part(data: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'HS256', 'typ': 'JWT'})}.{part({'exp': exp})}.signature"


class TestTokenAuth:
    def test_logs_in_lazily(self) -> None:
        auth = TokenAuth("api", "secret")
        assert auth.needs_login()
        assert auth.authorization() is None
        assert auth.login_body() == {"username": "api", "password": "secret"}

        auth.accept_login({"token": "abc"})
        assert not auth.needs_login()
        assert auth.authorization() == "Token abc"

    def test_rejected_token_needs_a_new_login(self) -> None:
        auth = TokenAuth("api", "secret")
        auth.accept_login({"token": "abc"})
        assert auth.needs_login(rejected="Token abc")
        # Someone else already logged in again: no second login.
        auth.accept_login({"token": "def"})
        assert not auth.needs_login(rejected="Token abc")

    def test_static_token_never_logs_in(self) -> None:
        auth = TokenAuth(token="abc")
        assert not auth.can_login
        assert not auth.needs_login(rejected="Token abc")
        assert auth.authorization() == "Token abc"

    def test_needs_credentials_or_token(self) -> None:
        with pytest.raises(ValueError, match="token"):
            TokenAuth("api")

    def test_login_response_without_token(self) -> None:
        with pytest.raises(ValueError, match="token"):
            TokenAuth("api", "secret").accept_login({"detail": "?"})

    def test_repr_hides_secrets(self) -> None:
        auth = TokenAuth("api", "hunter2")
        auth.accept_login({"token": "0123456789abcdef"})
        text = repr(auth)
        assert "hunter2" not in text
        assert "0123456789abcdef" not in text
        assert "api" in text

    def test_suspension(self) -> None:
        auth = TokenAuth("api", "secret")
        assert auth.suspended_for() == 0
        auth.suspend(30)
        assert 29 < auth.suspended_for() <= 30


class TestJWTAuth:
    def test_header_scheme(self) -> None:
        auth = JWTAuth("api", "secret")
        token = make_jwt(time.time() + 3600)
        auth.accept_login({"token": token})
        assert auth.authorization() == f"JWT {token}"
        assert not auth.needs_login()

    def test_logs_in_again_before_expiry(self) -> None:
        auth = JWTAuth("api", "secret", refresh_margin=60)
        auth.accept_login({"token": make_jwt(time.time() + 30)})
        assert auth.needs_login()

    def test_unreadable_token_is_used_until_rejected(self) -> None:
        auth = JWTAuth("api", "secret")
        auth.accept_login({"token": "not-a-jwt"})
        assert not auth.needs_login()


def test_staff_variants_use_staff_endpoints() -> None:
    assert StaffTokenAuth.login_path == "/staff-api-token-auth/"
    assert StaffJWTAuth.login_path == "/staff-jwt-api-token-auth/"
    assert TokenAuth.login_path == "/api-token-auth/"
    assert JWTAuth.login_path == "/jwt-api-token-auth/"


def test_basic_auth() -> None:
    auth = BasicAuth("api", "secret")
    assert auth.authorization() == "Basic " + base64.b64encode(b"api:secret").decode()
    assert not auth.can_login
    assert "secret" not in repr(auth)
