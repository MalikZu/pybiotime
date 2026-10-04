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
