"""Each BioTime version's payloads must read into the same models.

`fixtures/versions/<version>.json` holds the same records in the shape each version
sends: terminals, transactions, employees, departments, areas, positions and, where
the version has them, resignations. The values are made up; the shapes follow the
manuals and, for 9.5, a live server.
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pytest

from pybiotime.compat import docs_title, employee_shape, guess_version
from pybiotime.enums import PunchState, ResignType, VerifyType
from pybiotime.models import (
    Area,
    Department,
    Employee,
    Position,
    Resign,
    Terminal,
    Transaction,
)

VERSIONS = ["8.0", "8.5", "9.0", "9.5"]
FIXTURES = Path(__file__).parent / "fixtures" / "versions"


def payloads(version: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / f"{version}.json").read_text())
    return data


def transaction_view(t: Transaction) -> tuple[Any, ...]:
    return (
        t.id,
        t.emp_code,
        t.punch_time,
        t.punch_state,
        t.verify_type,
        t.terminal_sn,
        t.upload_time,
    )


def terminal_view(t: Terminal) -> tuple[Any, ...]:
    area = t.area.id if t.area else None
    return (t.id, t.sn, t.alias, t.ip_address, t.state, area, t.transfer_interval, t.is_attendance)


def employee_view(e: Employee) -> tuple[Any, ...]:
    attendance = e.attendance
    flags = (
        (attendance.enable_attendance, attendance.enable_overtime, attendance.enable_holiday)
        if attendance
        else None
    )
    return (
        e.id,
        e.emp_code,
        e.first_name,
        e.last_name,
        e.department_id,
        e.department.dept_name if e.department else None,
        e.position_id,
        e.position.position_name if e.position else None,
        sorted(e.area_ids),
        sorted(area.area_name or "" for area in e.area),
        e.hire_date,
        e.gender,
        e.verify_mode,
        e.emp_type,
        flags,
        e.device_password,
        e.card_no,
    )


def coded_view(item: Department | Area | Position) -> tuple[Any, ...]:
    if isinstance(item, Department):
        parent = item.parent_dept
        return (
            item.id,
            item.dept_code,
            item.dept_name,
            parent.id if parent else None,
            parent.dept_name if parent else None,
        )
    if isinstance(item, Area):
        parent_area = item.parent_area
        return (item.id, item.area_code, item.area_name, parent_area.id if parent_area else None)
    parent_position = item.parent_position
    return (
        item.id,
        item.position_code,
        item.position_name,
        parent_position.id if parent_position else None,
    )


def views(version: str) -> dict[str, list[tuple[Any, ...]]]:
    data = payloads(version)
    return {
        "terminals": [terminal_view(Terminal.model_validate(x)) for x in data["terminals"]],
        "transactions": [
            transaction_view(Transaction.model_validate(x)) for x in data["transactions"]
        ],
        "employees": [employee_view(Employee.model_validate(x)) for x in data["employees"]],
        "departments": [coded_view(Department.model_validate(x)) for x in data["departments"]],
        "areas": [coded_view(Area.model_validate(x)) for x in data["areas"]],
        "positions": [coded_view(Position.model_validate(x)) for x in data["positions"]],
    }


@pytest.mark.parametrize("version", VERSIONS)
def test_every_version_reads_into_the_same_models(version: str) -> None:
    assert views(version) == views("9.5")


def test_the_shared_records() -> None:
    """Pin the 9.5 reading, which every other version is compared with."""
    data = views("9.5")
    punch = data["transactions"][0]
    assert punch == (
        101,
        "1001",
        datetime(2026, 7, 28, 8, 0),
        PunchState.CHECK_IN,
        VerifyType.FINGERPRINT,
        "TEST0000001",
        datetime(2026, 7, 28, 8, 0, 5),
    )
    employee = data["employees"][0]
    assert employee[:10] == (
        41,
        "1001",
        "Test",
        "User",
        3,
        "Operations",
        5,
        "Technician",
        [1, 2],
        ["Head office", "Warehouse"],
    )
    assert employee[10] == date(2026, 10, 1)
    assert employee[14] == (True, False, True)
    assert data["departments"] == [(3, "OPS", "Operations", 2, "Head office")]
    assert data["areas"] == [(2, "WH", "Warehouse", 1)]


@pytest.mark.parametrize("version", VERSIONS)
def test_resignations_where_the_version_has_them(version: str) -> None:
    data = payloads(version)
    resigns = [Resign.model_validate(x) for x in data["resigns"]]
    assert bool(resigns) is data["has_resigns"]
    for resign in resigns:
        assert resign.employee.emp_code == "1001"
        assert resign.resign_type == ResignType.QUIT
        assert resign.resign_date == date(2026, 6, 4)


@pytest.mark.parametrize("version", VERSIONS)
def test_secrets_stay_out_of_repr(version: str) -> None:
    text = repr(Employee.model_validate(payloads(version)["employees"][0]))
    for secret in ("4321", "99887766", "pbkdf2"):
        assert secret not in text


@pytest.mark.parametrize(
    ("version", "mask", "temperature"),
    [("8.0", None, 0.0), ("8.5", False, 36.5), ("9.0", None, 255.0), ("9.5", None, 0.0)],
)
def test_mask_and_temperature(version: str, mask: bool | None, temperature: float) -> None:
    punch = Transaction.model_validate(payloads(version)["transactions"][0])
    assert punch.is_mask is mask
    assert punch.temperature == temperature


@pytest.mark.parametrize("version", VERSIONS)
def test_custom_attributes_are_kept(version: str) -> None:
    employee = Employee.model_validate(payloads(version)["employees"][0])
    custom = {"9.0": "CNIC", "9.5": "Global ID"}.get(version)
    if custom:
        assert custom in employee.extra
    for moved in ("attemployee", "enable_att", "dept_name", "area_name", "position_name"):
        assert moved not in employee.extra


class TestVersionSignals:
    @pytest.mark.parametrize("version", VERSIONS)
    def test_guess_from_the_fixture(self, version: str) -> None:
        data = payloads(version)
        page = f"<html><head><title>{data['docs_title']}</title></head></html>"
        shape = employee_shape(data["employees"][0])
        assert shape == ("flat" if version.startswith("8") else "nested")
        assert guess_version(docs_title(page), shape, data["has_resigns"]) == version

    def test_title_number_wins(self) -> None:
        assert guess_version("BioTime 9.5 API DOCS", "flat", False) == "9.5"

    def test_generation_only(self) -> None:
        assert guess_version("BIOTIME API DOCS", None, None) == "8.x"
        assert guess_version("ZKBio Time API DOCS", None, None) == "9.x"
        assert guess_version(None, "nested", None) == "9.x"
        assert guess_version(None, None, None) is None

    def test_title_parsing(self) -> None:
        page = "<HTML><TITLE>\n  BioTime   9.5 API DOCS </TITLE></HTML>"
        assert docs_title(page) == "BioTime 9.5 API DOCS"
        assert docs_title("<html>no title</html>") is None

    def test_shape_of_something_else(self) -> None:
        assert employee_shape({"id": 1}) is None
        assert employee_shape([]) is None
