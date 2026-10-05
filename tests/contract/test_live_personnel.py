"""Personnel checks against a real BioTime server. Skipped unless configured.

The read-only tests need the same variables as test_live.py. The round trip also needs
BIOTIME_WRITE_TESTS=1: it creates a department, area, position and employee whose codes
start with "PYBT", changes them, and deletes them again.
"""

import os
import secrets
import time
from collections.abc import Iterator
from datetime import date, timedelta

import pytest

from pybiotime import (
    APIError,
    BioTimeClient,
    BioTimeError,
    NotFoundError,
    ResignType,
    ServerInfo,
)
from tests.contract.test_live import URL, live_auth

pytestmark = pytest.mark.skipif(not URL, reason="BIOTIME_URL is not set")

ROOT = "/personnel/api/"
# What employees refer to, so it is deleted after them.
CODED = (("departments", "dept_code"), ("areas", "area_code"), ("positions", "position_code"))


@pytest.fixture(scope="module")
def client() -> Iterator[BioTimeClient]:
    assert URL
    with BioTimeClient(URL, auth=live_auth(), page_size=200) as live:
        yield live


@pytest.fixture(scope="module")
def info(client: BioTimeClient) -> ServerInfo:
    return client.server_info()


@pytest.mark.parametrize("resource", ["departments", "areas", "positions"])
def test_coded_resources_read(client: BioTimeClient, resource: str) -> None:
    manager = getattr(client, resource)
    items = list(manager.list())
    assert len(items) == manager.list().count()
    for item in items[:5]:
        code = getattr(item, manager.code_field)
        assert manager.get_by_code(code) == item
        assert manager.get(item.id).id == item.id


def test_every_employee_parses_and_is_found_by_code(client: BioTimeClient) -> None:
    employees = list(client.employees.list())
    assert len(employees) == client.employees.list().count()
    for employee in employees[:20]:
        found = client.employees.get_by_code(employee.emp_code)
        assert found is not None
        assert found.id == employee.id


def test_resigns_read(client: BioTimeClient, info: ServerInfo) -> None:
    if not info.has_resigns:
        pytest.skip("this server has no resign API, or did not say")
    for resign in client.resigns.list():
        assert client.resigns.get(resign.id).id == resign.id


@pytest.mark.skipif(
    os.environ.get("BIOTIME_WRITE_TESTS") != "1", reason="BIOTIME_WRITE_TESTS is not 1"
)
def test_round_trip(client: BioTimeClient, info: ServerInfo) -> None:
    tag = "PYBT" + secrets.token_hex(3).upper()
    # A code to rename to. Clean-up looks for both, in case a rename sticks.
    other = tag + "X"
    employee_ids: list[int] = []
    resign_ids: list[int] = []
    try:
        dept = client.departments.create(tag, f"{tag} department")
        area = client.areas.create(tag, f"{tag} area")
        position = client.positions.create(tag, f"{tag} position")

        assert client.departments.upsert(tag, f"{tag} department").id == dept.id
        renamed = client.departments.upsert(tag, f"{tag} renamed")
        assert renamed.dept_name == f"{tag} renamed"

        emp = client.employees.create(
            tag, department_id=dept.id, area_ids=[area.id], first_name="Test", last_name=tag
        )
        employee_ids.append(emp.id)
        assert emp.department_id == dept.id
        assert emp.area_ids == [area.id]

        same = client.employees.upsert(
            tag, department_id=dept.id, area_ids=[area.id], first_name="Test"
        )
        assert same.id == emp.id
        updated = client.employees.upsert(
            tag, department_id=dept.id, area_ids=[area.id], position_id=position.id
        )
        assert updated.position_id == position.id

        # BioTime 9.5 keeps department and employee codes, and says so only by
        # answering with the old one. update() must turn that into an error.
        with pytest.raises(APIError, match="kept"):
            client.departments.update(dept.id, code=other)
        assert client.departments.get(dept.id).dept_code == tag
        with pytest.raises(APIError, match="kept"):
            client.employees.update(emp.id, emp_code=other)
        assert client.employees.get(emp.id).emp_code == tag
        # Area and position codes do change. Rename them back for the clean-up.
        for manager, item, field in (
            (client.areas, area, "area_code"),
            (client.positions, position, "position_code"),
        ):
            assert getattr(manager.update(item.id, code=other), field) == other
            assert getattr(manager.update(item.id, code=tag), field) == tag

        if info.has_resigns:
            resign = client.resigns.create(
                emp.id,
                resign_date=date.today(),
                resign_type=ResignType.QUIT,
                reason="pybiotime test",
            )
            resign_ids.append(resign.id)
            assert resign.employee.id == emp.id
            # An update sends only some fields. The others must keep their values.
            earlier = date.today() - timedelta(days=1)
            moved = client.resigns.update(resign.id, resign_date=earlier)
            assert moved.resign_date == earlier
            assert moved.resign_type == ResignType.QUIT
            assert moved.disableatt is True
            client.resigns.reinstate([resign.id])
            assert all(r.id != resign.id for r in client.resigns.list(employee_id=emp.id))
    finally:
        left = clean_up(client, (tag, other), employee_ids, resign_ids)
        assert not left, f"Delete these test records by hand: {left}"


def clean_up(
    client: BioTimeClient, codes: tuple[str, ...], employee_ids: list[int], resign_ids: list[int]
) -> list[str]:
    """Delete what the round trip made, then return what is still there.

    Every step runs even when an earlier one failed, and lookups read raw JSON, so a bug
    in the code under test cannot stop the clean-up. Records are also found by each of
    `codes`, in case a step failed before their id was known or a rename stuck.
    """

    def by_code(kind: str, key: str) -> list[int]:
        return [i for code in codes for i in ids(client, kind, key, code)]

    employees = {*employee_ids, *by_code("employees", "emp_code")}
    resigns = {*resign_ids, *(r for e in employees for r in ids(client, "resigns", "employee", e))}
    paths = [f"resigns/{r}/" for r in resigns] + [f"employees/{e}/" for e in employees]
    paths += [f"{kind}/{i}/" for kind, key in CODED for i in by_code(kind, key)]
    for path in paths:
        delete(client, path)
    left = {path for path in paths if exists(client, path)}
    for kind, key in (("employees", "emp_code"), *CODED):
        left.update(f"{kind}/{i}/" for i in by_code(kind, key))
    return sorted(left)


def ids(client: BioTimeClient, kind: str, key: str, value: object) -> list[int]:
    """Ids of the records whose `key` is exactly `value`. Empty if the server fails."""
    params = {key: str(value), "page_size": "100"}
    try:
        body = client._request("GET", f"{ROOT}{kind}/", params=params)
    except BioTimeError:
        return []
    found = []
    for row in body.get("data", []) if isinstance(body, dict) else []:
        field = row.get(key)
        if isinstance(field, dict):
            field = field.get("id")
        if str(field) == str(value):
            found.append(row["id"])
    return found


def delete(client: BioTimeClient, path: str) -> None:
    # The client does not retry deletes, so retry here.
    for attempt in range(3):
        try:
            client._request("DELETE", ROOT + path)
            return
        except NotFoundError:
            return
        except BioTimeError:
            if attempt < 2:
                time.sleep(2)


def exists(client: BioTimeClient, path: str) -> bool:
    try:
        client._request("GET", ROOT + path)
    except NotFoundError:
        return False
    except BioTimeError:
        return True  # Cannot tell, so report it.
    return True
