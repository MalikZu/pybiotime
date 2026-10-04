"""Personnel checks against a real BioTime server. Skipped unless configured.

The read-only tests need the same variables as test_live.py. The round trip also needs
BIOTIME_WRITE_TESTS=1: it creates a department, area, position and employee whose codes
start with "PYBT", changes them, and deletes them again.
"""

import contextlib
import os
import secrets
from collections.abc import Iterator
from datetime import date

import pytest

from pybiotime import BioTimeClient, NotFoundError, ResignType
from tests.contract.test_live import URL, live_auth

pytestmark = pytest.mark.skipif(not URL, reason="BIOTIME_URL is not set")


@pytest.fixture(scope="module")
def client() -> Iterator[BioTimeClient]:
    assert URL
    with BioTimeClient(URL, auth=live_auth(), page_size=200) as live:
        yield live


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


def test_resigns_read(client: BioTimeClient) -> None:
    for resign in client.resigns.list():
        assert client.resigns.get(resign.id).id == resign.id


@pytest.mark.skipif(
    os.environ.get("BIOTIME_WRITE_TESTS") != "1", reason="BIOTIME_WRITE_TESTS is not 1"
)
def test_round_trip(client: BioTimeClient) -> None:
    tag = "PYBT" + secrets.token_hex(3).upper()
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

        resign = client.resigns.create(
            emp.id, resign_date=date.today(), resign_type=ResignType.QUIT, reason="pybiotime test"
        )
        assert resign.employee.id == emp.id
        client.resigns.reinstate([resign.id])
        assert all(r.id != resign.id for r in client.resigns.list(employee_id=emp.id))
    finally:
        # Clean up by code, so records are removed even when a step failed before
        # its id was known. Employees go first: they refer to the others.
        employee = client.employees.get_by_code(tag)
        if employee is not None:
            client.employees.delete(employee.id)
        for kind in ("departments", "areas", "positions"):
            manager = getattr(client, kind)
            leftover = manager.get_by_code(tag)
            if leftover is not None:
                with contextlib.suppress(NotFoundError):
                    manager.delete(leftover.id)
    assert client.employees.get_by_code(tag) is None
    for kind in ("departments", "areas", "positions"):
        assert getattr(client, kind).get_by_code(tag) is None
