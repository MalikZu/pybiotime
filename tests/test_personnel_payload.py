import json
from datetime import date, datetime

from pybiotime._personnel import employee_changes, employee_payload, resign_payload
from pybiotime.enums import EmploymentType
from pybiotime.models import Employee
from tests.test_models_personnel import employee


def test_dates_are_sent_as_dates() -> None:
    body = employee_payload(
        hire_date=datetime(2026, 10, 1, 8, 30), fields={"Contract end": date(2027, 1, 1)}
    )
    assert body == {"hire_date": "2026-10-01", "Contract end": "2027-01-01"}
    assert resign_payload(resign_date=datetime(2026, 10, 31, 17, 0)) == {
        "resign_date": "2026-10-31"
    }


def test_app_status_is_sent_as_a_number() -> None:
    # Compare the JSON: in Python, True == 1.
    assert json.dumps(employee_payload(app_status=True)) == '{"app_status": 1}'


def test_values_compare_as_the_server_stores_them() -> None:
    emp = Employee.model_validate(
        employee("9.5") | {"verify_mode": -1, "emp_type": 1, "Global ID": "17"}
    )
    desired = {
        "verify_mode": "-1",
        "emp_type": EmploymentType.OFFICIAL,
        "Global ID": 17,
        "area": [1, 1],
        "first_name": "Test ",
        "hire_date": "2026-10-01",
    }
    assert employee_changes(emp, desired) == {}
    assert employee_changes(emp, {"first_name": "Sara"}) == {"first_name": "Sara"}


def test_attendance_flags_compare_in_either_shape() -> None:
    old = Employee.model_validate(employee("8.0"))
    flags = {"enable_att": True, "enable_overtime": False, "enable_holiday": True}
    assert employee_changes(old, flags) == {}
    new = Employee.model_validate(employee("9.5"))
    assert employee_changes(new, {"attemployee": {"enable_overtime": True}}) == {}
    change = {"attemployee": {"enable_schedule": True}}
    assert employee_changes(new, change) == change


def test_fields_the_server_does_not_send_back_are_left_out() -> None:
    desired = {"self_password": "default-123", "flow_role": []}
    assert employee_changes(Employee.model_validate(employee("9.5")), desired) == {}
    # BioTime 8.x sends a password hash, which never equals the password.
    assert employee_changes(Employee.model_validate(employee("8.0")), desired) == {}
