import pytest

from pybiotime import AsyncBioTimeClient, FaultPageError, TokenAuth
from pybiotime.testing import VERSIONS, FakeBioTime

BASE = "http://biotime.test"
TITLES = {
    "8.0": "BIOTIME API DOCS",
    "8.5": "BIOTIME API DOCS",
    "9.0": "ZKBio Time API DOCS",
    "9.5": "BioTime 9.5 API DOCS",
}


def client_for(fake: FakeBioTime) -> AsyncBioTimeClient:
    return AsyncBioTimeClient(BASE, auth=TokenAuth("api", "secret"), transport=fake.transport())


def seeded(version: str) -> FakeBioTime:
    fake = FakeBioTime(version=version)
    dept = fake.add_department(code="OPS", name="Operations")
    area = fake.add_area(code="1", name="Head office")
    fake.add_employee(emp_code="1001", department_id=dept, area_ids=[area])
    return fake


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.anyio
async def test_detects_each_version(version: str) -> None:
    async with client_for(seeded(version)) as client:
        info = await client.server_info()
    assert info.version == version
    assert info.docs_title == TITLES[version]
    assert info.employee_shape == ("flat" if version.startswith("8") else "nested")
    assert info.has_resigns is (version in ("8.5", "9.5"))


@pytest.mark.parametrize(
    ("version", "expected"), [("8.0", "8.x"), ("8.5", "8.x"), ("9.0", "9.x"), ("9.5", "9.5")]
)
@pytest.mark.anyio
async def test_without_employees_only_the_title_counts(version: str, expected: str) -> None:
    async with client_for(FakeBioTime(version=version)) as client:
        info = await client.server_info()
    assert info.version == expected
    assert info.employee_shape is None


@pytest.mark.parametrize("version", ["8.0", "9.0"])
@pytest.mark.anyio
async def test_resigns_on_a_version_without_them(version: str) -> None:
    async with client_for(seeded(version)) as client:
        with pytest.raises(FaultPageError):
            await client.resigns.list().first()


@pytest.mark.anyio
async def test_lists_send_limit_beside_page_size() -> None:
    fake = seeded("9.5")
    async with client_for(fake) as client:
        await client.employees.list(page_size=50).first_page()
    sent = fake.requests[-1].params
    assert sent["page_size"] == sent["limit"] == "50"


def test_unknown_fake_version() -> None:
    with pytest.raises(ValueError, match="version"):
        FakeBioTime(version="7.0")
