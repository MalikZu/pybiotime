"""Payloads for personnel writes, with no network code. Shared by both clients."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from enum import Enum
from typing import Any

from pybiotime._core import DATETIME_FORMAT
from pybiotime._secret import Secret
from pybiotime.compat import _FLAT_ATTENDANCE
from pybiotime.errors import APIError
from pybiotime.models import Employee

# Keyword arguments whose API field has another name.
_RENAMED = {"department_id": "department", "area_ids": "area", "position_id": "position"}

# Read as a hash (8.x) or not at all (9.5), so it can never be compared.
_WRITE_ONLY = {"self_password"}

# Sent as `Secret`, so they stay out of tracebacks that show local variables.
_SECRET_FIELDS = {"device_password", "card_no", "self_password"}

# Employee properties that give the ids behind a relation.
_IDS = {"department": "department_id", "position": "position_id", "area": "area_ids"}

_UNKNOWN = object()


def employee_payload(fields: Mapping[str, Any] | None = None, **values: Any) -> dict[str, Any]:
    """Build an employee body from keyword arguments. ``None`` values are left out.

    `fields` is sent as given, so it can also clear a field with ``None``. Dates in it
    are sent as text.
    """
    body: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        name = _RENAMED.get(key, key)
        if isinstance(value, date):
            value = _day(value)
        elif name == "area":
            value = list(value)
        elif name == "emp_code":
            value = value.strip()
        elif name == "app_status":
            # BioTime takes 1 or 0 here, and rejects true and false.
            value = int(value)
        body[name] = value
    if fields:
        body.update({key: _wire(value) for key, value in fields.items()})
    for key in _SECRET_FIELDS & body.keys():
        if isinstance(body[key], str):
            body[key] = Secret(body[key])
    return body


def hide_secrets(
    card_no: str | None, device_password: str | None, fields: Mapping[str, Any] | None
) -> tuple[str | None, str | None, Mapping[str, Any] | None]:
    """Wrap the caller's secret arguments in `Secret` before anything can fail.

    The write methods rebind their parameters to these, so a traceback that shows
    local variables shows them redacted.
    """

    def hide(value: str | None) -> str | None:
        return Secret(value) if isinstance(value, str) else value

    if fields is not None:
        fields = {
            key: hide(value) if key in _SECRET_FIELDS else value for key, value in fields.items()
        }
    return hide(card_no), hide(device_password), fields


def employee_changes(existing: Employee, desired: Mapping[str, Any]) -> dict[str, Any]:
    """Return the part of `desired` that differs from `existing`.

    Fields the server does not send back, such as passwords, cannot be compared, so
    they are left out.
    """
    changes: dict[str, Any] = {}
    for key, value in desired.items():
        current = _current(existing, key)
        if current is not _UNKNOWN and not _same(current, value):
            changes[key] = value
    return changes


def code_kept_error(path: str, field: str, kept: str) -> APIError:
    """The error for an update whose new code the server ignored, as BioTime 9.5 does."""
    message = (
        f"PATCH {path}: the server kept {field} {kept!r}, so it does not change this code. "
        "Any other changes were saved."
    )
    return APIError(message, status_code=200, method="PATCH", path=path, detail=message)


def resign_payload(**values: Any) -> dict[str, Any]:
    names = {"employee_id": "employee", "disable_attendance": "disableatt"}
    return {
        names.get(key, key): _day(value) if isinstance(value, date) else value
        for key, value in values.items()
        if value is not None
    }


def _day(value: date) -> str:
    """Text for a date field. A datetime counts as its date: BioTime rejects the time."""
    if isinstance(value, datetime):
        value = value.date()
    return value.isoformat()


def _wire(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.strftime(DATETIME_FORMAT)
    if isinstance(value, date):
        return value.isoformat()
    return value


def _current(employee: Employee, key: str) -> Any:
    """The server's value for `key`, or `_UNKNOWN` when it did not send one."""
    if key in _WRITE_ONLY:
        return _UNKNOWN
    if key == "attemployee" or key in _FLAT_ATTENDANCE:
        # Both shapes of the attendance flags are read into `attendance`.
        if employee.attendance is None:
            return _UNKNOWN
        flags = employee.attendance.model_dump()
        return flags if key == "attemployee" else flags[_FLAT_ATTENDANCE[key]]
    if key in Employee.model_fields:
        if key not in employee.model_fields_set:
            return _UNKNOWN
        return getattr(employee, _IDS.get(key, key))
    return employee.extra.get(key, _UNKNOWN)


def _same(current: Any, wanted: Any) -> bool:
    current, wanted = _plain(current), _plain(wanted)
    if isinstance(wanted, Mapping):
        return isinstance(current, Mapping) and all(
            _same(current.get(key), value) for key, value in wanted.items()
        )
    if isinstance(wanted, (list, tuple, set, frozenset)):
        # Order and repeats do not matter: [1, 1] stores the same areas as [1].
        return isinstance(current, (list, tuple)) and _bag(current) == _bag(wanted)
    # BioTime sends "" and null interchangeably for empty text.
    if _blank(current) and _blank(wanted):
        return True
    if current is None or wanted is None:
        return False
    # Compare as stored: BioTime keeps 17 as "17", reads "-1" as -1 and trims text.
    return str(current).strip() == str(wanted).strip()


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, bool):
        return int(value)
    return _wire(value)


def _bag(values: Any) -> set[str]:
    return {str(_plain(value)).strip() for value in values}


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())
