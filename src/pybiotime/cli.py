"""The ``pybiotime`` command: read a BioTime server from a shell or a scheduled job.

Connection settings come from options or environment variables, so secrets stay out
of shell history:

    BIOTIME_URL        server address, for example http://10.0.0.5:8090
    BIOTIME_TOKEN      an API token, or:
    BIOTIME_USERNAME   with BIOTIME_PASSWORD (asked for when missing and in a terminal)
    BIOTIME_TIMEZONE   the server's timezone, for example Asia/Dubai
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import getpass
import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import IO, Any

from pybiotime import __version__
from pybiotime._sync import BioTimeClient
from pybiotime.auth import Auth, JWTAuth, TokenAuth
from pybiotime.errors import BioTimeError
from pybiotime.models import Employee, Terminal, Transaction

__all__ = ["main"]

# Never written out: the device PIN, the card number and the password hash.
_SECRETS = {"device_password", "card_no", "self_password"}

_TRANSACTION_COLUMNS = (
    "id",
    "emp_code",
    "punch_time",
    "punch_state",
    "punch_state_display",
    "verify_type",
    "verify_type_display",
    "terminal_sn",
    "terminal_alias",
    "upload_time",
)
_EMPLOYEE_COLUMNS = (
    "id",
    "emp_code",
    "first_name",
    "last_name",
    "department_code",
    "department_name",
    "position_code",
    "position_name",
    "area_codes",
    "hire_date",
    "emp_type",
    "app_status",
)
_TERMINAL_COLUMNS = (
    "id",
    "sn",
    "alias",
    "ip_address",
    "state",
    "area_code",
    "last_activity",
    "is_attendance",
)


class UsageError(Exception):
    """A missing or wrong setting. Exits with status 2."""


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command. Returns the exit status: 0 done, 1 BioTime error, 2 usage error."""
    parser = _parser()
    args = parser.parse_args(argv)
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    try:
        with connect(args) as client:
            handler: Callable[[BioTimeClient, argparse.Namespace], None] = args.handler
            handler(client, args)
    except UsageError as exc:
        parser.print_usage(sys.stderr)
        sys.stderr.write(f"pybiotime: error: {exc}\n")
        return 2
    except BioTimeError as exc:
        sys.stderr.write(f"pybiotime: {exc}\n")
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


def connect(args: argparse.Namespace) -> BioTimeClient:
    """Build the client from options and environment variables."""
    url = args.url or os.environ.get("BIOTIME_URL")
    if not url:
        raise UsageError("set --url or BIOTIME_URL")
    verify: bool | str = not args.insecure
    if args.ca_bundle:
        verify = args.ca_bundle
    return BioTimeClient(
        url,
        auth=_auth(args),
        timezone=args.timezone or os.environ.get("BIOTIME_TIMEZONE") or None,
        timeout=args.timeout,
        verify=verify,
    )


def _auth(args: argparse.Namespace) -> Auth:
    token = os.environ.get("BIOTIME_TOKEN")
    if token:
        return TokenAuth(token=token)
    username = args.username or os.environ.get("BIOTIME_USERNAME")
    if not username:
        raise UsageError("set BIOTIME_TOKEN, or BIOTIME_USERNAME and BIOTIME_PASSWORD")
    password = os.environ.get("BIOTIME_PASSWORD")
    if password is None:
        if not sys.stdin.isatty():
            raise UsageError("set BIOTIME_PASSWORD")
        password = getpass.getpass(f"BioTime password for {username}: ")
    return JWTAuth(username, password) if args.jwt else TokenAuth(username, password)


# --- commands -----------------------------------------------------------------------


def _info(client: BioTimeClient, args: argparse.Namespace) -> None:
    info = client.server_info()
    record = {
        "version": info.version,
        "docs_title": info.docs_title,
        "employee_shape": info.employee_shape,
        "has_resigns": info.has_resigns,
    }
    with _output(args) as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _terminals(client: BioTimeClient, args: argparse.Namespace) -> None:
    _write(args, (_terminal_record(t, args.format) for t in client.terminals.list()))


def _employees(client: BioTimeClient, args: argparse.Namespace) -> None:
    employees = client.employees.list(emp_code=args.emp_code, department_id=args.department_id)
    _write(args, (_employee_record(e, args.format) for e in employees))


def _transactions(client: BioTimeClient, args: argparse.Namespace) -> None:
    punches = client.transactions.list(
        start=args.start,
        end=args.end,
        emp_code=args.emp_code,
        terminal_sn=args.terminal_sn,
        order_by="punch_time",
    )
    _write(args, (_transaction_record(p, args.format) for p in punches))


def _sync(client: BioTimeClient, args: argparse.Namespace) -> None:
    state_path = Path(args.state)
    state = json.loads(state_path.read_text()) if state_path.exists() else None
    result = client.transactions.read_new(
        state, start=args.start, lookback=timedelta(hours=args.lookback_hours)
    )
    # Write the punches first. The state moves on only once they are safely out, so a
    # crash repeats work instead of losing it.
    _write(args, (_transaction_record(p, args.format) for p in result.transactions))
    _save_atomically(state_path, json.dumps(result.state))
    if args.verbose:
        sys.stderr.write(f"pybiotime: {len(result.transactions)} new punch(es)\n")


# --- records ------------------------------------------------------------------------


def _transaction_record(punch: Transaction, fmt: str) -> dict[str, Any]:
    record = punch.model_dump(mode="json")
    return {key: record.get(key) for key in _TRANSACTION_COLUMNS} if fmt == "csv" else record


def _employee_record(employee: Employee, fmt: str) -> dict[str, Any]:
    if fmt != "csv":
        return employee.model_dump(mode="json", exclude=_SECRETS)
    department, position = employee.department, employee.position
    return {
        "id": employee.id,
        "emp_code": employee.emp_code,
        "first_name": employee.first_name,
        "last_name": employee.last_name,
        "department_code": department.dept_code if department else None,
        "department_name": department.dept_name if department else None,
        "position_code": position.position_code if position else None,
        "position_name": position.position_name if position else None,
        "area_codes": ";".join(a.area_code or str(a.id) for a in employee.area),
        "hire_date": employee.hire_date.isoformat() if employee.hire_date else None,
        "emp_type": employee.emp_type,
        "app_status": employee.app_status,
    }


def _terminal_record(terminal: Terminal, fmt: str) -> dict[str, Any]:
    record = terminal.model_dump(mode="json")
    if fmt != "csv":
        return record
    record["area_code"] = terminal.area.area_code if terminal.area else None
    return {key: record.get(key) for key in _TERMINAL_COLUMNS}


# --- output -------------------------------------------------------------------------


@contextlib.contextmanager
def _output(args: argparse.Namespace) -> Iterator[IO[str]]:
    """Standard output, or the --output file: appended to by sync, replaced otherwise."""
    if not args.output:
        yield sys.stdout
        sys.stdout.flush()
        return
    mode = "a" if args.command == "sync" else "w"
    with open(args.output, mode, encoding="utf-8", newline="") as stream:
        yield stream
        stream.flush()
        os.fsync(stream.fileno())


def _write(args: argparse.Namespace, records: Iterable[dict[str, Any]]) -> None:
    with _output(args) as stream:
        _write_to(stream, args, records)


def _write_to(stream: IO[str], args: argparse.Namespace, records: Iterable[dict[str, Any]]) -> None:
    if args.format == "csv":
        columns = {
            "transactions": _TRANSACTION_COLUMNS,
            "sync": _TRANSACTION_COLUMNS,
            "employees": _EMPLOYEE_COLUMNS,
            "terminals": _TERMINAL_COLUMNS,
        }[args.command]
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator="\n")
        # An appended file already has its header.
        if args.command != "sync" or not args.output or stream.tell() == 0:
            writer.writeheader()
        writer.writerows(records)
    else:
        for record in records:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _save_atomically(path: Path, text: str) -> None:
    """Replace `path` in one step, so a crash never leaves half a state file."""
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent or ".", prefix=f".{path.name}.", delete=False, encoding="utf-8"
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(handle.name, path)


# --- arguments ----------------------------------------------------------------------


def _when(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"{value!r} is not a date or time; use 2026-10-01 or '2026-10-01 08:00'"
        ) from None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pybiotime",
        description="Read a ZKTeco BioTime server. Unofficial; not affiliated with ZKTeco.",
        epilog="Settings: BIOTIME_URL, BIOTIME_TOKEN or BIOTIME_USERNAME and "
        "BIOTIME_PASSWORD, BIOTIME_TIMEZONE.",
    )
    parser.add_argument("--version", action="version", version=f"pybiotime {__version__}")
    parser.add_argument("--url", help="server address (default: $BIOTIME_URL)")
    parser.add_argument("--username", help="log in as this user (default: $BIOTIME_USERNAME)")
    parser.add_argument("--jwt", action="store_true", help="log in for a JSON Web Token")
    parser.add_argument("--timezone", help="the server's timezone (default: $BIOTIME_TIMEZONE)")
    parser.add_argument("--timeout", type=float, default=60.0, help="seconds per request")
    parser.add_argument("--ca-bundle", help="trust the certificates in this file")
    parser.add_argument("--insecure", action="store_true", help="do not check the TLS certificate")
    parser.add_argument("-v", "--verbose", action="store_true", help="log requests to stderr")
    commands = parser.add_subparsers(dest="command", required=True, metavar="command")

    def command(name: str, handler: Callable[..., None], help_text: str) -> Any:
        sub = commands.add_parser(name, help=help_text, description=help_text)
        sub.set_defaults(handler=handler)
        sub.add_argument(
            "-o",
            "--output",
            help="write to this file instead of standard output (sync appends to it)",
        )
        return sub

    command("info", _info, "Show which BioTime version the server seems to run.")

    for name, handler, help_text in (
        ("terminals", _terminals, "List devices."),
        ("employees", _employees, "List employees. PINs, card numbers and hashes are left out."),
        ("transactions", _transactions, "Export punches, oldest first."),
        ("sync", _sync, "Print punches that arrived since the last run, then save the state."),
    ):
        sub = command(name, handler, help_text)
        sub.add_argument(
            "--format", choices=("jsonl", "csv"), default="jsonl", help="output format"
        )
        if name == "employees":
            sub.add_argument("--emp-code", help="only this employee")
            sub.add_argument("--department-id", type=int, help="only this department")
        if name == "transactions":
            sub.add_argument("--start", type=_when, help="punched at or after this time")
            sub.add_argument("--end", type=_when, help="punched at or before this time")
            sub.add_argument("--emp-code", help="only this employee")
            sub.add_argument("--terminal-sn", help="only this device")
        if name == "sync":
            sub.add_argument(
                "--state", required=True, help="JSON file that remembers what was read"
            )
            sub.add_argument(
                "--start", type=_when, help="first run only: punches from this time on"
            )
            sub.add_argument(
                "--lookback-hours",
                type=float,
                default=24.0,
                help="hours of punch times to read again as a safety net (default 24)",
            )
    return parser
