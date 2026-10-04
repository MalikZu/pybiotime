"""Unofficial typed Python client for the ZKTeco BioTime REST API."""

from pybiotime._async import AsyncBioTimeClient, AsyncPager
from pybiotime._sync import BioTimeClient, Pager
from pybiotime._version import __version__
from pybiotime.auth import BasicAuth, JWTAuth, StaffJWTAuth, StaffTokenAuth, TokenAuth
from pybiotime.enums import PunchState, VerifyType
from pybiotime.errors import (
    APIError,
    AuthenticationError,
    BadRequestError,
    BioTimeError,
    FaultPageError,
    LicenseError,
    LoginSuspendedError,
    NotFoundError,
    PaginationError,
    PermissionDeniedError,
    ResponseShapeError,
    ServerError,
    TransportError,
)
from pybiotime.models import Terminal, Transaction
from pybiotime.pagination import Page

__all__ = [
    "APIError",
    "AsyncBioTimeClient",
    "AsyncPager",
    "AuthenticationError",
    "BadRequestError",
    "BasicAuth",
    "BioTimeClient",
    "BioTimeError",
    "FaultPageError",
    "JWTAuth",
    "LicenseError",
    "LoginSuspendedError",
    "NotFoundError",
    "Page",
    "Pager",
    "PaginationError",
    "PermissionDeniedError",
    "PunchState",
    "ResponseShapeError",
    "ServerError",
    "StaffJWTAuth",
    "StaffTokenAuth",
    "Terminal",
    "TokenAuth",
    "Transaction",
    "TransportError",
    "VerifyType",
    "__version__",
]
