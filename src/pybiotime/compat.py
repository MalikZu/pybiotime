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
from dataclasses import dataclass
from typing import Any, Literal

__all__ = [
    "EmployeeShape",
    "ServerInfo",
    "docs_title",
    "employee_shape",
    "guess_version",
    "normalize_department",
    "normalize_employee",
]

EmployeeShape = Literal["nested", "flat"]


@dataclass(frozen=True)
class ServerInfo:
    """What a BioTime server shows about itself. See `BioTimeClient.server_info`."""

    #: The version in the docs page title, such as "9.5"; "8.x" when only flat employees
    #: show the generation; ``None`` when nothing tells.
    version: str | None
    #: Title of the public API docs page, if the server serves one.
    docs_title: str | None
    #: "flat" (8.x) or "nested" (9.x and later 8.x builds) attendance flags; ``None``
    #: without employees.
    employee_shape: EmployeeShape | None
    #: Whether the resign API exists. BioTime 8.5 and 9.5 have it.
    has_resigns: bool


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


def normalize_department(data: Any) -> Any:
    """Move BioTime 8.x's ``parent_dept_name`` into the ``parent_dept`` reference.

    8.x sends the parent as an id with its name beside it; 9.x expands the parent.
    """
    if not isinstance(data, dict) or "parent_dept_name" not in data:
        return data
    data = dict(data)
    _fold(data, "parent_dept", "dept_name", data.pop("parent_dept_name"))
    return data


def _fold_names(data: dict[str, Any]) -> None:
    for relation, key in _RELATION_NAMES.items():
        if key in data:
            _fold(data, relation, key, data.pop(key))

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


def _fold(data: dict[str, Any], relation: str, key: str, name: Any) -> None:
    """Put `name` under `key` in the `relation` reference, keeping a name it already has."""
    ref = data.get(relation)
    if isinstance(ref, dict):
        data[relation] = {key: name, **ref}
    elif ref is not None:
        data[relation] = {"id": ref, key: name}


def page_params(size: int) -> dict[str, str]:
    """Query parameters asking for `size` objects per page.

    BioTime takes ``page_size``; the 8.0 and 9.0 manuals document ``limit`` instead.
    Servers ignore parameters they do not know, so both are sent.
    """
    return {"page_size": str(size), "limit": str(size)}


_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TITLE = re.compile(r"<title(?:\s[^>]*)?>(.*?)</title\s*>", re.IGNORECASE | re.DOTALL)
# The number right after the product name, as in "BioTime 9.5" or "ZKBioTime8.0".
_VERSION = re.compile(r"(?:biotime|zkbio\s*time)\s*v?\s*([0-9]+\.[0-9]+)", re.IGNORECASE)


def docs_title(page: str) -> str | None:
    """The title of the server's public ``/api/docs/`` page, or ``None`` for another page.

    It is "BioTime 9.5 API DOCS" on a live 9.5 server. The manuals show
    "BIOTIME API DOCS" for 8.x and "ZKBio Time API DOCS" for 9.0. Other titles, such as
    that of the "Page not found" page BioTime serves for unknown paths, give ``None``.
    """
    for match in _TITLE.finditer(_COMMENT.sub("", page)):
        title = " ".join(html.unescape(match.group(1)).split())
        if "api docs" in title.lower():
            return title
    return None


def employee_shape(employee: Any) -> EmployeeShape | None:
    """Whether an employee payload nests its attendance flags (9.x) or not (8.x)."""
    if not isinstance(employee, dict):
        return None
    if isinstance(employee.get("attemployee"), dict):
        return "nested"
    if any(key in employee for key in _FLAT_ATTENDANCE):
        return "flat"
    return None


def guess_version(title: str | None, shape: EmployeeShape | None) -> str | None:
    """The BioTime version, as far as what the server shows can tell.

    A version number after the product name in the docs title gives it. Otherwise flat
    attendance flags show an 8.x server, and nothing else is certain: some 8.x servers
    nest the flags as 9.x does, the product names overlap, and the resign API is not
    tied to one version.
    """
    if title:
        number = _VERSION.search(title)
        if number:
            return number.group(1)
    return "8.x" if shape == "flat" else None
