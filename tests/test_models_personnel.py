import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from pybiotime.enums import ResignType
from pybiotime.models import (
    Area,
    Department,
    Employee,
    EmployeeAttendance,
    Position,
    Resign,
)

FIXTURES = Path(__file__).parent / "fixtures"


def employee(version: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / version / "employees.json").read_text())
    return dict(data["data"][0])


def personnel(kind: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / "9.5" / "personnel.json").read_text())
    return dict(data[kind][0])


class TestEmployee:
    def test_9_5_shape(self) -> None:
        emp = Employee.model_validate(employee("9.5"))
        assert emp.emp_code == "1001"
        assert emp.department_id == 3
        assert emp.area_ids == [1]
        assert emp.position_id is None
        assert emp.hire_date == date(2026, 10, 1)
        assert emp.attendance == EmployeeAttendance(
            enable_attendance=True,
            enable_overtime=True,
            enable_holiday=True,
            enable_schedule=False,
        )
        assert emp.extra["Global ID"] == "GID-0001"
        assert "attemployee" not in emp.extra

    def test_8_0_shape_gives_the_same_fields(self) -> None:
        emp = Employee.model_validate(employee("8.0"))
        assert emp.department_id == 3
        assert emp.area_ids == [1, 2]
        assert emp.attendance == EmployeeAttendance(
            enable_attendance=True, enable_overtime=False, enable_holiday=True
        )
        assert "enable_att" not in emp.extra

    def test_can_be_hashed(self) -> None:
        emp = Employee.model_validate(employee("9.5"))
        assert hash(emp) == hash(Employee.model_validate(employee("9.5")))

    @pytest.mark.parametrize("version", ["9.5", "8.0"])
    def test_secrets_stay_out_of_repr(self, version: str) -> None:
        emp = Employee.model_validate(employee(version))
        text = repr(emp)
        for secret in ("4321", "99887766", "pbkdf2"):
            assert secret not in text
        assert "1001" in text

    def test_secrets_are_still_readable(self) -> None:
        emp = Employee.model_validate(employee("9.5"))
        assert emp.device_password == "4321"
        assert emp.card_no == "99887766"

    def test_missing_area(self) -> None:
        payload = employee("9.5") | {"area": None}
        assert Employee.model_validate(payload).area == ()

    def test_no_attendance_flags(self) -> None:
        payload = employee("9.5")
        del payload["attemployee"]
        assert Employee.model_validate(payload).attendance is None


def test_department() -> None:
    dept = Department.model_validate(personnel("departments"))
    assert dept.dept_code == "OPS"
    assert dept.parent_dept is not None
    assert dept.parent_dept.id == 2


def test_department_with_bare_parent_id() -> None:
    dept = Department.model_validate(personnel("departments") | {"parent_dept": 2})
    assert dept.parent_dept is not None
    assert dept.parent_dept.id == 2


def test_area() -> None:
    area = Area.model_validate(personnel("areas"))
    assert area.parent_area is not None
    assert area.parent_area.area_code == "1"
    assert area.parent_area_name == "Head office"


def test_position() -> None:
    assert Position.model_validate(personnel("positions")).parent_position is None


def test_resign() -> None:
    resign = Resign.model_validate(personnel("resigns"))
    assert resign.employee.emp_code == "1001"
    assert resign.resign_type == ResignType.QUIT
    assert resign.resign_date == date(2026, 6, 4)
    assert resign.disableatt is True
