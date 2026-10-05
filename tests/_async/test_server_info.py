import httpx
import pytest

from pybiotime import AsyncBioTimeClient, FaultPageError, TokenAuth
from pybiotime.testing import VERSIONS, FakeBioTime
from pybiotime.testing._personnel import _PROFILES

BASE = "http://biotime.test"
# What the signals can tell: a number in the docs title, or flat employees.
EXPECTED = {"8.0": "8.x", "8.5": "8.x", "9.0": None, "9.5": "9.5"}


def client_for(
    fake: FakeBioTime, transport: httpx.MockTransport | None = None
) -> AsyncBioTimeClient:
    return AsyncBioTimeClient(
        BASE,
        auth=TokenAuth("api", "secret"),
        transport=transport or fake.transport(),
        retries=0,
    )


def seeded(version: str, resign_api: bool | None = None) -> FakeBioTime:
    fake = FakeBioTime(version=version, resign_api=resign_api)
    dept = fake.add_department(code="OPS", name="Operations")
    area = fake.add_area(code="1", name="Head office")
    fake.add_employee(emp_code="1001", department_id=dept, area_ids=[area])
    return fake


def serving(fake: FakeBioTime, path: str, page: bytes) -> httpx.MockTransport:
    """The fake's transport, except that `path` answers with an HTML `page`."""

    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == path:
            return httpx.Response(200, content=page, headers={"Content-Type": "text/html"})
        return fake.handle(request)

    return httpx.MockTransport(handle)


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.anyio
async def test_detects_each_version(version: str) -> None:
    fake = seeded(version)
    async with client_for(fake) as client:
        info = await client.server_info()
    profile = _PROFILES[version]
    assert info.version == EXPECTED[version]
    assert info.docs_title == profile.docs_title
    assert info.employee_shape == ("flat" if profile.flat else "nested")
    assert info.has_resigns is fake.has_resigns


@pytest.mark.parametrize(
    ("version", "expected"), [("8.0", None), ("8.5", None), ("9.0", None), ("9.5", "9.5")]
)
@pytest.mark.anyio
async def test_without_employees_only_a_numbered_title_counts(
    version: str, expected: str | None
) -> None:
    async with client_for(FakeBioTime(version=version)) as client:
        info = await client.server_info()
    assert info.version == expected
    assert info.employee_shape is None


@pytest.mark.parametrize(("version", "expected"), [("8.0", "8.x"), ("9.0", None)])
@pytest.mark.anyio
async def test_the_resign_api_does_not_pick_the_version(version: str, expected: str) -> None:
    # Servers differ from their manuals: an 8.0 or 9.0 with the resign API is not 8.5 or 9.5.
    async with client_for(seeded(version, resign_api=True)) as client:
        info = await client.server_info()
    assert info.has_resigns is True
    assert info.version == expected


@pytest.mark.parametrize("version", ["8.0", "9.0"])
@pytest.mark.anyio
async def test_another_page_at_the_docs_path_is_not_a_docs_title(version: str) -> None:
    fake = seeded(version)
    page = b"<html><head><title>Page not found</title></head></html>"
    async with client_for(fake, serving(fake, "/api/docs/", page)) as client:
        info = await client.server_info()
    assert info.docs_title is None
    assert info.version == EXPECTED[version]


@pytest.mark.parametrize("version", [v for v in VERSIONS if not _PROFILES[v].resign_api])
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
    fake = FakeBioTime()
    fake.version = "8.x"
    with pytest.raises(ValueError, match="version"):
        _ = fake.has_resigns
