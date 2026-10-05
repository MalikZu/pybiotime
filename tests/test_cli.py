import argparse
import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from pybiotime import BioTimeClient, JWTAuth, TokenAuth, cli
from pybiotime.testing import FakeBioTime

ENV = ("BIOTIME_URL", "BIOTIME_TOKEN", "BIOTIME_USERNAME", "BIOTIME_PASSWORD", "BIOTIME_TIMEZONE")


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeBioTime:
    server = FakeBioTime()
    server.add_terminal(sn="TEST0000001", alias="Main gate")
    dept = server.add_department(code="OPS", name="Operations")
    area = server.add_area(code="1", name="Head office")
    server.add_employee(
        emp_code="1001",
        department_id=dept,
        area_ids=[area],
        first_name="Sara",
        card_no="99887766",
        device_password="4321",
    )
    for minute in range(3):
        server.add_transaction(
            emp_code="1001", punch_time=datetime(2026, 10, 1, 8, minute), terminal_sn="TEST0000001"
        )

    def connect(args: argparse.Namespace) -> BioTimeClient:
        return BioTimeClient(
            "http://biotime.test", auth=TokenAuth("api", "secret"), transport=server.transport()
        )

    monkeypatch.setattr(cli, "connect", connect)
    return server


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    status = cli.main(list(argv))
    captured = capsys.readouterr()
    return status, captured.out, captured.err


def lines(out: str) -> list[dict[str, object]]:
    return [json.loads(line) for line in out.splitlines()]


def test_info(fake: FakeBioTime, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "info")
    assert status == 0
    assert json.loads(out)["version"] == "9.5"


def test_terminals_as_csv(fake: FakeBioTime, capsys: pytest.CaptureFixture[str]) -> None:
    status, out, _ = run(capsys, "terminals", "--format", "csv")
    assert status == 0
    rows = list(csv.DictReader(io.StringIO(out)))
    assert rows[0]["sn"] == "TEST0000001"
    assert rows[0]["area_code"] == "1"


@pytest.mark.parametrize("fmt", ["jsonl", "csv"])
def test_employees_leave_secrets_out(
    fake: FakeBioTime, capsys: pytest.CaptureFixture[str], fmt: str
) -> None:
    status, out, _ = run(capsys, "employees", "--format", fmt)
    assert status == 0
    assert "1001" in out
    assert "Operations" in out
    for secret in ("99887766", "4321", "card_no", "device_password"):
        assert secret not in out


def test_transactions_from_a_start_time(
    fake: FakeBioTime, capsys: pytest.CaptureFixture[str]
) -> None:
    status, out, _ = run(capsys, "transactions", "--start", "2026-10-01 08:01")
    assert status == 0
    assert [p["punch_time"] for p in lines(out)] == ["2026-10-01T08:01:00", "2026-10-01T08:02:00"]


def test_sync_returns_each_punch_once(
    fake: FakeBioTime, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    state = tmp_path / "state.json"
    status, out, _ = run(capsys, "sync", "--state", str(state))
    assert status == 0
    assert len(lines(out)) == 3
    assert json.loads(state.read_text())["max_id"] is not None

    _, again, _ = run(capsys, "sync", "--state", str(state))
    assert again == ""

    fake.add_transaction(emp_code="1001", punch_time=datetime(2026, 10, 1, 9, 0))
    _, new, _ = run(capsys, "sync", "--state", str(state))
    assert [p["punch_time"] for p in lines(new)] == ["2026-10-01T09:00:00"]


def test_sync_appends_csv_with_one_header(
    fake: FakeBioTime, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    state, out = tmp_path / "state.json", tmp_path / "punches.csv"
    args = ("sync", "--state", str(state), "--format", "csv", "--output", str(out))
    run(capsys, *args)
    fake.add_transaction(emp_code="1001", punch_time=datetime(2026, 10, 1, 9, 0))
    run(capsys, *args)
    rows = list(csv.DictReader(io.StringIO(out.read_text())))
    assert len(rows) == 4
    assert out.read_text().count("emp_code") == 1


def test_sync_keeps_the_state_when_reading_fails(
    fake: FakeBioTime, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    state = tmp_path / "state.json"
    run(capsys, "sync", "--state", str(state))
    before = state.read_text()
    fake.add_transaction(emp_code="1001", punch_time=datetime(2026, 10, 1, 9, 0))
    fake.tokens.clear()
    fake.password = "changed"
    status, out, err = run(capsys, "sync", "--state", str(state))
    assert status == 1
    assert "rejected the login" in err
    assert out == ""
    assert state.read_text() == before


def test_export_to_a_file_replaces_it(
    fake: FakeBioTime, capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    target = tmp_path / "punches.jsonl"
    target.write_text("old\n")
    status, out, _ = run(capsys, "transactions", "-o", str(target))
    assert status == 0
    assert out == ""
    assert len(lines(target.read_text())) == 3


def test_a_bad_time_is_a_usage_error(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as caught:
        cli.main(["transactions", "--start", "yesterday"])
    assert caught.value.code == 2
    assert "not a date" in capsys.readouterr().err


class TestSettings:
    def test_url_is_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        status, _, err = run(capsys, "info")
        assert status == 2
        assert "BIOTIME_URL" in err

    def test_credentials_are_required(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("BIOTIME_URL", "http://biotime.test")
        status, _, err = run(capsys, "info")
        assert status == 2
        assert "BIOTIME_TOKEN" in err

    def test_token_from_the_environment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BIOTIME_URL", "http://biotime.test")
        monkeypatch.setenv("BIOTIME_TOKEN", "abc")
        with cli.connect(cli._parser().parse_args(["info"])) as client:
            assert isinstance(client.auth, TokenAuth)
            assert client.auth.authorization() == "Token abc"

    def test_password_login_with_jwt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BIOTIME_URL", "http://biotime.test")
        monkeypatch.setenv("BIOTIME_USERNAME", "api")
        monkeypatch.setenv("BIOTIME_PASSWORD", "secret")
        monkeypatch.setenv("BIOTIME_TIMEZONE", "Asia/Dubai")
        with cli.connect(cli._parser().parse_args(["--jwt", "info"])) as client:
            assert isinstance(client.auth, JWTAuth)
            assert client.timezone is not None
