"""Differences between BioTime versions, smoothed into one shape.

Models call these before validation, so callers see the same fields whatever the
server version. Add a function here, with a fixture per version, when a new
difference turns up.

The version helpers at the end read the signals a server gives about its version.
No endpoint reports the version itself.
"""

from __future__ import annotations

import html
import re
from typing import Any, Literal

__all__ = ["EmployeeShape", "docs_title", "employee_shape", "guess_version", "normalize_employee"]

EmployeeShape = Literal["nested", "flat"]

# BioTime 8.x sends these at the top level of an employee.
_FLAT_ATTENDANCE = {
    "enable_att": "enable_attendance",
    "enable_overtime": "enable_overtime",
    "enable_holiday": "enable_holiday",
}

# BioTime 8.x repeats the related object's name beside these relations.
_RELATION_NAMES = {"department": "dept_name", "position": "position_name"}


def normalize_employee(data: Any) -> Any:
    """Move the attendance flags into one ``attendance`` object, and names into references.

    BioTime 9.x nests the flags under ``attemployee`` (``enable_attendance``,
    ``enable_overtime``, ``enable_holiday``, ``enable_schedule``). BioTime 8.x sends
    ``enable_att``, ``enable_overtime`` and ``enable_holiday`` at the top level.

    BioTime 8.x also sends ``dept_name``, ``position_name`` and ``area_name`` (names
    joined by commas) beside the relations. They move into the references, where 9.x
    has them.
    """
    if not isinstance(data, dict) or "attendance" in data:
        return data
    data = dict(data)
    _fold_names(data)
    nested = data.pop("attemployee", None)
    if isinstance(nested, dict):
        data["attendance"] = {key: value for key, value in nested.items() if key != "id"}
        return data
    flat = {new: data.pop(old) for old, new in _FLAT_ATTENDANCE.items() if old in data}
    if flat:
        data["attendance"] = flat
    return data


def _fold_names(data: dict[str, Any]) -> None:
    for relation, key in _RELATION_NAMES.items():
        if key not in data:
            continue
        name = data.pop(key)
        ref = data.get(relation)
        if isinstance(ref, dict):
            data[relation] = {key: name, **ref}
        elif ref is not None:
            data[relation] = {"id": ref, key: name}

    areas, names = data.get("area"), data.get("area_name")
    if not isinstance(areas, list) or "area_name" not in data:
        return
    if all(isinstance(area, dict) for area in areas):
        del data["area_name"]
    elif isinstance(names, str) and len(names.split(",")) == len(areas):
        # A name with a comma in it would not split right; then it stays in `extra`.
        del data["area_name"]
        data["area"] = [
            {"id": area, "area_name": name}
            for area, name in zip(areas, names.split(","), strict=True)
        ]


_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_VERSION = re.compile(r"\b(\d+\.\d+)\b")


def docs_title(page: str) -> str | None:
    """The title of the server's public ``/api/docs/`` page.

    It is "BioTime 9.5 API DOCS" on a live 9.5 server. The manuals show
    "BIOTIME API DOCS" for 8.x and "ZKBio Time API DOCS" for 9.0.
    """
    match = _TITLE.search(page)
    if match is None:
        return None
    title = " ".join(html.unescape(match.group(1)).split())
    return title or None


def employee_shape(employee: Any) -> EmployeeShape | None:
    """Whether an employee payload nests its attendance flags (9.x) or not (8.x)."""
    if not isinstance(employee, dict):
        return None
    if isinstance(employee.get("attemployee"), dict):
        return "nested"
    if any(key in employee for key in _FLAT_ATTENDANCE):
        return "flat"
    return None


def guess_version(
    title: str | None, shape: EmployeeShape | None, has_resigns: bool | None
) -> str | None:
    """Best guess at the BioTime version from what the server shows.

    A version number in the docs title wins. Otherwise the employee shape and the
    resign API decide, as the manuals describe them: 8.0 flat without resigns,
    8.5 flat with resigns, 9.0 nested without resigns, 9.5 nested with resigns.
    Returns "8.x" or "9.x" when only the generation is clear, and ``None`` when
    nothing is.
    """
    if title:
        number = _VERSION.search(title)
        if number:
            return number.group(1)
    if shape is None:
        if title and "zkbio" in title.lower():
            return "9.x"
        if title and "biotime" in title.lower():
            return "8.x"
        return None
    generation = "8" if shape == "flat" else "9"
    if has_resigns is None:
        return f"{generation}.x"
    minor = "5" if has_resigns else "0"
    return f"{generation}.{minor}"
