"""Ways to authenticate with BioTime.

Pick one and pass it to the client:

- `TokenAuth`: logs in once for a token that does not expire. The default choice.
- `JWTAuth`: logs in for a JSON Web Token and logs in again shortly before it expires.
- `BasicAuth`: sends the username and password with every request. Some licences
  without the API module still accept it.
- `StaffTokenAuth`, `StaffJWTAuth`: the same, for employee self-service accounts.

The client logs in lazily on the first request, and once more if the server rejects
the token. Secrets never appear in `repr()`.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from typing import Any, ClassVar

__all__ = [
    "Auth",
    "BasicAuth",
    "JWTAuth",
    "StaffJWTAuth",
    "StaffTokenAuth",
    "TokenAuth",
]

_REDACTED = "<redacted>"


class Auth:
    """Base class for authentication methods. Use one of the subclasses."""

    #: Endpoint that exchanges a username and password for a token, if any.
    login_path: ClassVar[str | None] = None

    def __init__(self) -> None:
        self._suspended_until = 0.0

    @property
    def can_login(self) -> bool:
        """Whether a rejected token can be replaced by logging in again."""
        return False

    def authorization(self) -> str | None:
        """The ``Authorization`` header value, or ``None`` when a login is needed."""
        raise NotImplementedError

    def needs_login(self, rejected: str | None = None) -> bool:
        """Whether to log in before the next request.

        `rejected` is a header value the server just refused. A login is needed only if
        it is still the current one, so concurrent callers log in once, not each.
        """
        return False

    def login_body(self) -> dict[str, str]:
        raise NotImplementedError

    def accept_login(self, body: Any) -> None:
        """Store the token from a successful login response."""
        raise NotImplementedError

    def suspended_for(self) -> float:
        """Seconds left before another login may be tried."""
        return max(0.0, self._suspended_until - time.monotonic())

    def suspend(self, seconds: float) -> None:
        self._suspended_until = time.monotonic() + seconds


class _LoginAuth(Auth):
    scheme: ClassVar[str]

    def __init__(self, username: str, password: str) -> None:
        super().__init__()
        self.username = username
        self._password = password
        self._token: str | None = None

    @property
    def can_login(self) -> bool:
        return True

    def authorization(self) -> str | None:
        return f"{self.scheme} {self._token}" if self._token else None

    def needs_login(self, rejected: str | None = None) -> bool:
        current = self.authorization()
        return current is None or current == rejected

    def login_body(self) -> dict[str, str]:
        return {"username": self.username, "password": self._password}

    def accept_login(self, body: Any) -> None:
        token = body.get("token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise ValueError("The login response did not contain a token")
        self._token = token

    def __repr__(self) -> str:
        token = _REDACTED if self._token else None
        return (
            f"{type(self).__name__}(username={self.username!r}, password={_REDACTED}, "
            f"token={token})"
        )


class TokenAuth(_LoginAuth):
    """Log in with a username and password for a token that does not expire.

    If you already have a token, pass it as `token=` and leave out the password.
    The client then never logs in, and a rejected token raises `AuthenticationError`.
    """

    login_path: ClassVar[str | None] = "/api-token-auth/"
    scheme = "Token"

    def __init__(
        self, username: str | None = None, password: str | None = None, *, token: str | None = None
    ) -> None:
        if token is None and (username is None or password is None):
            raise ValueError("Pass a username and password, or a token")
        super().__init__(username or "", password or "")
        self._token = token
        self._static = password is None

    @property
    def can_login(self) -> bool:
        return not self._static

    def needs_login(self, rejected: str | None = None) -> bool:
        return not self._static and super().needs_login(rejected)


class JWTAuth(_LoginAuth):
    """Log in with a username and password for a JSON Web Token.

    The client reads the token's expiry and logs in again `refresh_margin` seconds before it.
    """

    login_path: ClassVar[str | None] = "/jwt-api-token-auth/"
    scheme = "JWT"

    def __init__(self, username: str, password: str, *, refresh_margin: float = 60.0) -> None:
        super().__init__(username, password)
        self.refresh_margin = refresh_margin
        self._expires_at: float | None = None

    def needs_login(self, rejected: str | None = None) -> bool:
        if super().needs_login(rejected):
            return True
        if self._expires_at is None:
            return False
        return time.time() >= self._expires_at - self.refresh_margin

    def accept_login(self, body: Any) -> None:
        super().accept_login(body)
        self._expires_at = _jwt_expiry(self._token or "")


class StaffTokenAuth(TokenAuth):
    """`TokenAuth` for an employee self-service account."""

    login_path: ClassVar[str | None] = "/staff-api-token-auth/"


class StaffJWTAuth(JWTAuth):
    """`JWTAuth` for an employee self-service account."""

    login_path: ClassVar[str | None] = "/staff-jwt-api-token-auth/"


class BasicAuth(Auth):
    """Send the username and password with every request (HTTP Basic)."""

    def __init__(self, username: str, password: str) -> None:
        super().__init__()
        self.username = username
        credentials = f"{username}:{password}".encode()
        self._header = "Basic " + base64.b64encode(credentials).decode("ascii")

    def authorization(self) -> str | None:
        return self._header

    def __repr__(self) -> str:
        return f"BasicAuth(username={self.username!r}, password={_REDACTED})"


def _jwt_expiry(token: str) -> float | None:
    """Read the ``exp`` claim without verifying the signature. We only need the time."""
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (IndexError, ValueError, binascii.Error):
        return None
    exp = claims.get("exp") if isinstance(claims, dict) else None
    return float(exp) if isinstance(exp, (int, float)) else None
