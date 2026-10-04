# Generated from tests/_async/test_personnel.py by scripts/unasync.py. Do not edit.

from datetime import date

import pytest

from pybiotime import (
    BadRequestError,
    BioTimeClient,
    NotFoundError,
    ResignType,
    TokenAuth,
)
from pybiotime.testing import FakeBioTime

BASE = "http://biotime.test"


@pytest.fixture
def fake() -> FakeBioTime:
    server = FakeBioTime()
    hq = server.add_department(code="HQ", name="Head office")
    server.add_department(code="OPS", name="Operations", parent_id=hq)
    server.add_department(code="OPS2", name="Operations two")
    server.add_area(code="1", name="Main site")
    server.add_area(code="10", name="Warehouse")
    server.add_position(code="TECH", name="Technician")
    return server


def client_for(fake: FakeBioTime) -> BioTimeClient:
    return BioTimeClient(BASE, auth=TokenAuth("api", "secret"), transport=fake.transport())


def writes(fake: FakeBioTime, method: str) -> int:
    return sum(1 for r in fake.requests if r.method == method)


def area_id(fake: FakeBioTime, code: str) -> int:
    return int(next(a["id"] for a in fake.areas if a["area_code"] == code))


def dept_id(fake: FakeBioTime, code: str) -> int:
    return int(next(d["id"] for d in fake.departments if d["dept_code"] == code))


class TestDepartments:
    def test_get_by_code_matches_exactly(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            ops = client.departments.get_by_code("OPS")
            missing = client.departments.get_by_code("OP")
        assert ops is not None
        assert ops.dept_name == "Operations"
        assert ops.parent_dept is not None
        assert ops.parent_dept.dept_code == "HQ"
        assert missing is None

    def test_create_update_delete(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            created = client.departments.create("FIN", "Finance")
            renamed = client.departments.update(created.id, name="Finance team")
            assert renamed.dept_name == "Finance team"
            assert renamed.dept_code == "FIN"
            client.departments.delete(created.id)
            with pytest.raises(NotFoundError):
                client.departments.get(created.id)

    def test_duplicate_code_is_a_bad_request(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            with pytest.raises(BadRequestError) as caught:
                client.departments.create("OPS", "Again")
        assert "dept_code" in caught.value.field_errors

    def test_upsert(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            created = client.departments.upsert("FIN", "Finance")
            same = client.departments.upsert("FIN", "Finance")
            assert writes(fake, "PATCH") == 0
            moved = client.departments.upsert("FIN", "Finance", parent_id=dept_id(fake, "HQ"))
        assert same.id == created.id
        assert moved.parent_dept is not None
        assert moved.parent_dept.dept_code == "HQ"
        creates = [r for r in fake.requests if r.method == "POST" and "departments" in r.path]
        assert len(creates) == 1
        assert writes(fake, "PATCH") == 1


@pytest.mark.parametrize(
    ("resource", "code_field"),
    [("areas", "area_code"), ("positions", "position_code")],
)
def test_areas_and_positions(fake: FakeBioTime, resource: str, code_field: str) -> None:
    with client_for(fake) as client:
        manager = getattr(client, resource)
        created = manager.upsert("NEW", "New one")
        found = manager.get_by_code("NEW")
        listed = [item for item in manager.list()]
    assert getattr(found, code_field) == "NEW"
    assert found.id == created.id
    assert created.id in [item.id for item in listed]


class TestEmployees:
    def test_create_and_read(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            created = client.employees.create(
                "1001",
                department_id=dept_id(fake, "OPS"),
                area_ids=[area_id(fake, "1")],
                first_name="Sara",
                hire_date=date(2026, 10, 1),
                card_no="99887766",
                fields={"Global ID": "GID-1"},
            )
            found = client.employees.get_by_code("1001")
        assert found is not None
        assert found.id == created.id
        assert created.attendance is not None
        assert found.department_id == dept_id(fake, "OPS")
        assert found.area_ids == [area_id(fake, "1")]
        assert found.hire_date == date(2026, 10, 1)
        assert found.attendance is not None
        assert found.extra["Global ID"] == "GID-1"
        assert "99887766" not in repr(found)
        sent = next(r.json for r in fake.requests if r.method == "POST" and "employees" in r.path)
        assert sent["department"] == dept_id(fake, "OPS")
        assert sent["area"] == [area_id(fake, "1")]
        assert sent["hire_date"] == "2026-10-01"

    def test_department_and_area_are_required(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            with pytest.raises(BadRequestError) as caught:
                client.employees.create("1001", department_id=999, area_ids=[])
        assert set(caught.value.field_errors) == {"department", "area"}

    def test_upsert_sends_only_what_changed(self, fake: FakeBioTime) -> None:
        ops, site = dept_id(fake, "OPS"), area_id(fake, "1")
        with client_for(fake) as client:
            first = client.employees.upsert(
                "1001", department_id=ops, area_ids=[site], first_name="Sara", email=""
            )
            again = client.employees.upsert(
                "1001", department_id=ops, area_ids=[site], first_name="Sara"
            )
            assert writes(fake, "PATCH") == 0
            changed = client.employees.upsert(
                "1001",
                department_id=ops,
                area_ids=[site, area_id(fake, "10")],
                first_name="Sarah",
            )
        assert first.id == again.id == changed.id
        assert changed.first_name == "Sarah"
        assert sorted(changed.area_ids) == sorted([site, area_id(fake, "10")])
        patch = next(r.json for r in fake.requests if r.method == "PATCH")
        assert set(patch) == {"area", "first_name"}

    def test_upsert_sets_write_only_fields_once(self, fake: FakeBioTime) -> None:
        kwargs = {"department_id": dept_id(fake, "OPS"), "area_ids": [area_id(fake, "1")]}
        with client_for(fake) as client:
            for _ in range(3):
                client.employees.upsert(
                    "1001",
                    fields={"self_password": "default-123"},
                    **kwargs,  # type: ignore[arg-type]
                )
        assert fake.employees[0]["self_password"] == "default-123"
        assert writes(fake, "PATCH") == 0

    def test_update_and_delete(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            created = client.employees.create(
                "1001", department_id=dept_id(fake, "OPS"), area_ids=[area_id(fake, "1")]
            )
            updated = client.employees.update(
                created.id, position_id=fake.positions[0]["id"], last_name="Ali"
            )
            assert updated.position is not None
            assert updated.position.position_code == "TECH"
            assert updated.last_name == "Ali"
            client.employees.delete(created.id)
            assert client.employees.get_by_code("1001") is None

    def test_duplicate_code(self, fake: FakeBioTime) -> None:
        kwargs = {"department_id": dept_id(fake, "OPS"), "area_ids": [area_id(fake, "1")]}
        with client_for(fake) as client:
            client.employees.create("1001", **kwargs)  # type: ignore[arg-type]
            with pytest.raises(BadRequestError) as caught:
                client.employees.create("1001", **kwargs)  # type: ignore[arg-type]
        assert "emp_code" in caught.value.field_errors


class TestResigns:
    def test_resign_and_reinstate(self, fake: FakeBioTime) -> None:
        with client_for(fake) as client:
            emp = client.employees.create(
                "1001", department_id=dept_id(fake, "OPS"), area_ids=[area_id(fake, "1")]
            )
            resign = client.resigns.create(
                emp.id, resign_date=date(2026, 10, 31), resign_type=ResignType.QUIT
            )
            assert resign.employee.emp_code == "1001"
            assert resign.disableatt is True
            listed = [r for r in client.resigns.list(employee_id=emp.id)]
            assert [r.id for r in listed] == [resign.id]

            moved = client.resigns.update(resign.id, resign_date=date(2026, 11, 1))
            assert moved.resign_date == date(2026, 11, 1)

            client.resigns.reinstate([resign.id])
            assert [r for r in client.resigns.list(employee_id=emp.id)] == []
        sent = next(
            r.json for r in fake.requests if r.method == "POST" and r.path.endswith("/resigns/")
        )
        assert sent == {
            "employee": emp.id,
            "resign_date": "2026-10-31",
            "resign_type": 1,
            "disableatt": True,
            "reason": "",
        }


@pytest.mark.parametrize("kind", ["departments", "areas", "positions"])
def test_create_without_id_in_the_answer_is_read_back(fake: FakeBioTime, kind: str) -> None:
    fake.creates_without_id = {kind}
    with client_for(fake) as client:
        created = getattr(client, kind).create("NEW", "New one")
    stored = next(r for r in getattr(fake, kind) if r["id"] == created.id)
    assert stored["id"] == created.id


def test_employee_and_resign_without_id_in_the_answer(fake: FakeBioTime) -> None:
    fake.creates_without_id = {"employees", "resigns"}
    with client_for(fake) as client:
        emp = client.employees.create(
            "1001", department_id=dept_id(fake, "OPS"), area_ids=[area_id(fake, "1")]
        )
        resign = client.resigns.create(
            emp.id, resign_date=date(2026, 10, 31), resign_type=ResignType.QUIT
        )
    assert emp.id == fake.employees[0]["id"]
    assert resign.id == fake.resigns[0]["id"]


def test_spaces_around_codes_do_not_count(fake: FakeBioTime) -> None:
    with client_for(fake) as client:
        position = client.positions.create("NEW ", "New one")
        ops = client.departments.upsert(" OPS ", "Operations ")
    assert position.position_code == "NEW"
    assert ops.id == dept_id(fake, "OPS")
    assert writes(fake, "PATCH") == 0
