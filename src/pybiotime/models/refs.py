"""References from one object to another.

BioTime sends a related object either expanded (``{"id": 1, "area_code": "1", ...}``)
or as a bare id (``1``), depending on the endpoint and version. A reference accepts
both: `id` is always set, the other fields only when the server expanded it.
"""

from __future__ import annotations

from typing import Any

from pydantic import model_validator

from pybiotime.models._base import BioTimeModel

__all__ = ["AreaRef", "DepartmentRef", "EmployeeRef", "PositionRef"]


class _Ref(BioTimeModel):
    id: int

    @model_validator(mode="before")
    @classmethod
    def _from_bare_id(cls, value: Any) -> Any:
        if isinstance(value, (int, str)) and not isinstance(value, bool):
            return {"id": value}
        return value


class AreaRef(_Ref):
    area_code: str | None = None
    area_name: str | None = None


class DepartmentRef(_Ref):
    dept_code: str | None = None
    dept_name: str | None = None


class PositionRef(_Ref):
    position_code: str | None = None
    position_name: str | None = None


class EmployeeRef(_Ref):
    emp_code: str | None = None
    first_name: str | None = None
    last_name: str | None = None
