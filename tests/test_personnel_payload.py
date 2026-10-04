import json
from datetime import date, datetime

from pybiotime._personnel import employee_payload, resign_payload


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
