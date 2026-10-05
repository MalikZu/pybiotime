"""Unofficial typed Python client for the ZKTeco BioTime REST API."""

from pybiotime._async import AsyncBioTimeClient, AsyncPager
from pybiotime._sync import BioTimeClient, Pager
from pybiotime._version import __version__
from pybiotime.auth import BasicAuth, JWTAuth, StaffJWTAuth, StaffTokenAuth, TokenAuth
from pybiotime.compat import ServerInfo
from pybiotime.enums import (
    DevicePrivilege,
    EmploymentType,
    PunchState,
    ResignType,
    VerifyType,
)
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
from pybiotime.incremental import ReadResult, ReadStateError
from pybiotime.models import (
    Area,
    Department,
    Employee,
    Position,
    Resign,
    Terminal,
    Transaction,
)
from pybiotime.pagination import Page

__all__ = [
    "APIError",
    "Area",
    "AsyncBioTimeClient",
    "AsyncPager",
    "AuthenticationError",
    "BadRequestError",
    "BasicAuth",
    "BioTimeClient",
    "BioTimeError",
    "Department",
    "DevicePrivilege",
    "Employee",
    "EmploymentType",
    "FaultPageError",
    "JWTAuth",
    "LicenseError",
    "LoginSuspendedError",
    "NotFoundError",
    "Page",
    "Pager",
    "PaginationError",
    "PermissionDeniedError",
    "Position",
    "PunchState",
    "ReadResult",
    "ReadStateError",
    "Resign",
    "ResignType",
    "ResponseShapeError",
    "ServerError",
    "ServerInfo",
    "StaffJWTAuth",
    "StaffTokenAuth",
    "Terminal",
    "TokenAuth",
    "Transaction",
    "TransportError",
    "VerifyType",
    "__version__",
]
