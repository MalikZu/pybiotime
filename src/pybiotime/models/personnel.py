from __future__ import annotations

from typing import Any

from pydantic import Field, field_validator, model_validator

from pybiotime.compat import normalize_employee
from pybiotime.models._base import (
    BioTimeModel,
    LenientBool,
    LenientInt,
    OptionalDate,
    OptionalDateTime,
)
from pybiotime.models.refs import AreaRef, DepartmentRef, EmployeeRef, PositionRef

__all__ = ["Area", "Department", "Employee", "EmployeeAttendance", "Position", "Resign"]


class Department(BioTimeModel):
    id: int
    dept_code: str
    dept_name: str
    parent_dept: DepartmentRef | None = None


class Area(BioTimeModel):
    id: int
    area_code: str
    area_name: str
    parent_area: AreaRef | None = None
    parent_area_name: str | None = None


class Position(BioTimeModel):
    id: int
    position_code: str
    position_name: str
    parent_position: PositionRef | None = None
    parent_position_name: str | None = None


class EmployeeAttendance(BioTimeModel):
    """Whether attendance rules apply to an employee. `None` when the server did not say."""

    enable_attendance: LenientBool = None
    enable_overtime: LenientBool = None
    enable_holiday: LenientBool = None
    #: Only BioTime 9.x reports this one.
    enable_schedule: LenientBool = None


class Employee(BioTimeModel):
    """A person known to BioTime. `emp_code` is the business key; devices use it too.

    `device_password`, `card_no` and `self_password` are secrets: they are left out of
    `repr()`. BioTime 8.x sends `self_password` as a password hash; 9.5 leaves it out.
    """

    id: int
    emp_code: str
    first_name: str | None = None
    last_name: str | None = None
    nickname: str | None = None
    #: BioTime 9.x only.
    full_name: str | None = None
    #: BioTime 9.x only.
    format_name: str | None = None
    department: DepartmentRef | None = None
    position: PositionRef | None = None
    #: An employee can belong to several areas.
    area: list[AreaRef] = Field(default_factory=list)
    attendance: EmployeeAttendance | None = None
    hire_date: OptionalDate = None
    birthday: OptionalDate = None
    #: "M", "F" or "O".
    gender: str | None = None
    #: Compare with `pybiotime.EmploymentType`.
    emp_type: LenientInt = None
    #: Compare with `pybiotime.VerifyType`; -1 means the device's default.
    verify_mode: LenientInt = None
    #: Compare with `pybiotime.DevicePrivilege`.
    dev_privilege: LenientInt = None
    #: 1 when the employee may use the mobile app.
    app_status: LenientInt = None
    #: 1 employee, 2 administrator.
    app_role: LenientInt = None
    email: str | None = None
    mobile: str | None = None
    contact_tel: str | None = None
    office_tel: str | None = None
    national: str | None = None
    city: str | None = None
    address: str | None = None
    postcode: str | None = None
    ssn: str | None = None
    religion: str | None = None
    #: Serial number of the device the person enrolled on.
    enroll_sn: str | None = None
    update_time: OptionalDateTime = None
    #: The PIN typed on devices. Sent in clear text by the server.
    device_password: str | None = Field(default=None, repr=False)
    card_no: str | None = Field(default=None, repr=False)
    self_password: str | None = Field(default=None, repr=False)

    @model_validator(mode="before")
    @classmethod
    def _smooth_versions(cls, data: Any) -> Any:
        return normalize_employee(data)

    @field_validator("area", mode="before")
    @classmethod
    def _area_list(cls, value: Any) -> Any:
        if value is None or value == "":
            return []
        if not isinstance(value, list):
            return [value]
        return value

    @property
    def department_id(self) -> int | None:
        return self.department.id if self.department else None

    @property
    def position_id(self) -> int | None:
        return self.position.id if self.position else None

    @property
    def area_ids(self) -> list[int]:
        return [area.id for area in self.area]


class Resign(BioTimeModel):
    """A resignation: the employee left, and may be reinstated later."""

    id: int
    employee: EmployeeRef
    resign_date: OptionalDate = None
    #: Compare with `pybiotime.ResignType`.
    resign_type: LenientInt = None
    #: Whether attendance stopped being calculated for the employee.
    disableatt: LenientBool = None
    reason: str | None = None
