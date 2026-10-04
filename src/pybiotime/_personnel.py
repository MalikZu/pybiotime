"""Payloads for personnel writes, with no network code. Shared by both clients."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Any

from pybiotime._core import DATETIME_FORMAT
from pybiotime.models import Employee

# Keyword arguments whose API field has another name.
_RENAMED = {"department_id": "department", "area_ids": "area", "position_id": "position"}


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
        elif name == "app_status":
            # BioTime takes 1 or 0 here, and rejects true and false.
            value = int(value)
        body[name] = value
    if fields:
        body.update({key: _wire(value) for key, value in fields.items()})
    return body


def employee_changes(existing: Employee, desired: Mapping[str, Any]) -> dict[str, Any]:
    """Return the part of `desired` that differs from `existing`."""
    return {
        key: value for key, value in desired.items() if not _same(_current(existing, key), value)
    }


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
    if key == "department":
        return employee.department_id
    if key == "position":
        return employee.position_id
    if key == "area":
        return employee.area_ids
    if key in Employee.model_fields:
        return getattr(employee, key)
    return employee.extra.get(key)


def _same(current: Any, wanted: Any) -> bool:
    if isinstance(current, date):
        current = current.isoformat()
    if isinstance(wanted, Sequence) and not isinstance(wanted, str):
        return isinstance(current, list) and sorted(current) == sorted(wanted)
    # BioTime sends "" and null interchangeably for empty text.
    if current in (None, "") and wanted in (None, ""):
        return True
    return bool(current == wanted)
