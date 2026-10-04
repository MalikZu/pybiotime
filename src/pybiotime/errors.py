"""Exceptions raised by pybiotime.

Every exception derives from `BioTimeError`, so one `except` clause can catch them all.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "BioTimeError",
    "FaultPageError",
    "LicenseError",
    "LoginSuspendedError",
    "NotFoundError",
    "PaginationError",
    "PermissionDeniedError",
    "ResponseShapeError",
    "ServerError",
    "TransportError",
]


class BioTimeError(Exception):
    """Base class for every pybiotime error."""


class TransportError(BioTimeError):
    """The request never got a response: connection refused, DNS failure, timeout, TLS error."""


class FaultPageError(BioTimeError):
    """The server answered with something that is not JSON.

    BioTime sometimes serves an HTML page with HTTP 200, for example for an unknown path
    or while the server is starting. This error keeps the start of the body for debugging.
    """

    def __init__(self, message: str, *, status_code: int, content_type: str, snippet: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.content_type = content_type
        self.snippet = snippet


class APIError(BioTimeError):
    """The server returned an error response.

    `detail` is the server's message when it sent one. `body` is the decoded JSON body.
    `code` is the envelope's `code` field when the server reported a failure with HTTP 200.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        method: str,
        path: str,
        detail: str | None = None,
        body: Any = None,
        code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.method = method
        self.path = path
        self.detail = detail
        self.body = body
        self.code = code


class AuthenticationError(APIError):
    """The credentials or the token were rejected."""


class LoginSuspendedError(AuthenticationError):
    """Logins are paused after the server rejected the credentials.

    Retrying a wrong password in a loop can lock the account, so the client waits
    `retry_after` seconds before it tries to log in again.
    """

    def __init__(self, message: str, *, retry_after: float, path: str) -> None:
        super().__init__(message, status_code=0, method="POST", path=path)
        self.retry_after = retry_after


class PermissionDeniedError(APIError):
    """HTTP 403: the account may not do this."""


class LicenseError(PermissionDeniedError):
    """HTTP 403 that mentions the licence, usually because it lacks the API module."""


class NotFoundError(APIError):
    """HTTP 404."""


class BadRequestError(APIError):
    """HTTP 400: the server rejected the request.

    `field_errors` maps each field name to its messages. Errors that are not tied to a
    field are under `"non_field_errors"`.
    """

    def __init__(
        self,
        message: str,
        *,
        field_errors: dict[str, list[str]],
        status_code: int,
        method: str,
        path: str,
        detail: str | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(
            message, status_code=status_code, method=method, path=path, detail=detail, body=body
        )
        self.field_errors = field_errors


class ServerError(APIError):
    """HTTP 5xx."""


class PaginationError(BioTimeError):
    """The server's pages did not make sense, for example the same page came back twice."""


class ResponseShapeError(BioTimeError):
    """A response was valid JSON but did not have the shape pybiotime expects."""
