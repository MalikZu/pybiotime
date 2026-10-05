# Generated from tests/_async/test_server_info.py by scripts/unasync.py. Do not edit.

import pytest

from pybiotime import BioTimeClient, FaultPageError, TokenAuth
from pybiotime.testing import VERSIONS, FakeBioTime
from pybiotime.testing._personnel import _PROFILES

BASE = "http://biotime.test"


def client_for(fake: FakeBioTime) -> BioTimeClient:
    return BioTimeClient(BASE, auth=TokenAuth("api", "secret"), transport=fake.transport())


def seeded(version: str) -> FakeBioTime:
    fake = FakeBioTime(version=version)
    dept = fake.add_department(code="OPS", name="Operations")
    area = fake.add_area(code="1", name="Head office")
    fake.add_employee(emp_code="1001", department_id=dept, area_ids=[area])
    return fake


@pytest.mark.parametrize("version", VERSIONS)
def test_detects_each_version(version: str) -> None:
    fake = seeded(version)
    with client_for(fake) as client:
        info = client.server_info()
    profile = _PROFILES[version]
    assert info.version == version
    assert info.docs_title == profile.docs_title
    assert info.employee_shape == ("flat" if profile.flat else "nested")
    assert info.has_resigns is fake.has_resigns


@pytest.mark.parametrize(
    ("version", "expected"), [("8.0", "8.x"), ("8.5", "8.x"), ("9.0", "9.x"), ("9.5", "9.5")]
)
def test_without_employees_only_the_title_counts(version: str, expected: str) -> None:
    with client_for(FakeBioTime(version=version)) as client:
        info = client.server_info()
    assert info.version == expected
    assert info.employee_shape is None


@pytest.mark.parametrize("version", [v for v in VERSIONS if not _PROFILES[v].resign_api])
def test_resigns_on_a_version_without_them(version: str) -> None:
    with client_for(seeded(version)) as client:
        with pytest.raises(FaultPageError):
            client.resigns.list().first()


def test_lists_send_limit_beside_page_size() -> None:
    fake = seeded("9.5")
    with client_for(fake) as client:
        client.employees.list(page_size=50).first_page()
    sent = fake.requests[-1].params
    assert sent["page_size"] == sent["limit"] == "50"


def test_unknown_fake_version() -> None:
    with pytest.raises(ValueError, match="version"):
        FakeBioTime(version="7.0")
    fake = FakeBioTime()
    fake.version = "8.x"
    with pytest.raises(ValueError, match="version"):
        _ = fake.has_resigns
