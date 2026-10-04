"""Differences between BioTime versions, smoothed into one shape.

Models call these before validation, so callers see the same fields whatever the
server version. Add a function here, with a fixture per version, when a new
difference turns up.
"""

from __future__ import annotations

from typing import Any

__all__ = ["normalize_employee"]

# BioTime 8.x sends these at the top level of an employee.
_FLAT_ATTENDANCE = {
    "enable_att": "enable_attendance",
    "enable_overtime": "enable_overtime",
    "enable_holiday": "enable_holiday",
}


def normalize_employee(data: Any) -> Any:
    """Move the attendance flags into one ``attendance`` object.

    BioTime 9.x nests them under ``attemployee`` (``enable_attendance``,
    ``enable_overtime``, ``enable_holiday``, ``enable_schedule``). BioTime 8.x sends
    ``enable_att``, ``enable_overtime`` and ``enable_holiday`` at the top level.
    """
    if not isinstance(data, dict) or "attendance" in data:
        return data
    data = dict(data)
    nested = data.pop("attemployee", None)
    if isinstance(nested, dict):
        data["attendance"] = {key: value for key, value in nested.items() if key != "id"}
        return data
    flat = {new: data.pop(old) for old, new in _FLAT_ATTENDANCE.items() if old in data}
    if flat:
        data["attendance"] = flat
    return data
