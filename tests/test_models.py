import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from pybiotime.enums import PunchState, VerifyType
from pybiotime.models import AreaRef, DepartmentRef, Terminal, Transaction

FIXTURES = Path(__file__).parent / "fixtures"


def items(version: str, name: str) -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads((FIXTURES / version / name).read_text())["data"]
    return data


class TestTransaction:
    def test_parses_a_9_5_payload(self) -> None:
        first, second = (Transaction.model_validate(i) for i in items("9.5", "transactions.json"))

        assert first.id == 101
        assert first.emp_code == "1001"
        assert first.punch_time == datetime(2026, 7, 28, 8, 0)
        assert first.punch_time.tzinfo is None
        assert first.punch_state == PunchState.CHECK_IN
        assert first.verify_type == VerifyType.ANY
        assert first.terminal_sn == ""
        assert first.is_mask is None
        assert first.temperature == 0.0
        assert first.upload_time == datetime(2026, 7, 29, 15, 8, 10)

        assert second.punch_state == "1"
        assert second.punch_state == PunchState.CHECK_OUT
        assert second.verify_type == VerifyType.FACE
        assert second.is_mask is True
        assert second.temperature == 36.6

    def test_undeclared_fields_go_to_extra(self) -> None:
        second = Transaction.model_validate(items("9.5", "transactions.json")[1])
        assert second.extra["department"] == "Operations"

    def test_timezone_from_context(self) -> None:
        dubai = ZoneInfo("Asia/Dubai")
        first = Transaction.model_validate(
            items("9.5", "transactions.json")[0], context={"timezone": dubai}
        )
        assert first.punch_time == datetime(2026, 7, 28, 8, 0, tzinfo=dubai)
        assert first.upload_time is not None
        assert first.upload_time.tzinfo is dubai

    def test_is_frozen(self) -> None:
        first = Transaction.model_validate(items("9.5", "transactions.json")[0])
        with pytest.raises(ValidationError):
            first.emp_code = "x"  # type: ignore[misc]

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            (0, False),
            (1, True),
            ("No", False),
            ("Yes", True),
            ("-", None),
            (255, None),
            (None, None),
        ],
    )
    def test_is_mask_values(self, raw: object, expected: bool | None) -> None:
        payload = items("9.5", "transactions.json")[0] | {"is_mask": raw}
        assert Transaction.model_validate(payload).is_mask is expected

    def test_blank_numbers_are_none(self) -> None:
        payload = items("9.5", "transactions.json")[0] | {"temperature": "", "verify_type": ""}
        parsed = Transaction.model_validate(payload)
        assert parsed.temperature is None
        assert parsed.verify_type is None


class TestTerminal:
    def test_parses_a_9_5_payload(self) -> None:
        terminal = Terminal.model_validate(items("9.5", "terminals.json")[0])
        assert terminal.sn == "TEST0000001"
        assert terminal.state == 1
        assert terminal.is_attendance is True
        assert terminal.area == AreaRef(id=1, area_code="1", area_name="Head office")
        assert terminal.last_activity == datetime(2026, 10, 3, 23, 23, 15)


class TestRefs:
    def test_bare_id(self) -> None:
        assert DepartmentRef.model_validate(3) == DepartmentRef(id=3)

    def test_expanded(self) -> None:
        ref = DepartmentRef.model_validate({"id": 3, "dept_code": "OPS", "dept_name": "Ops"})
        assert (ref.id, ref.dept_code, ref.dept_name) == (3, "OPS", "Ops")
