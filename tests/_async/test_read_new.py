import json
from datetime import datetime, timedelta

import pytest

from pybiotime import AsyncBioTimeClient, TokenAuth
from pybiotime.incremental import RECENT_ID_SPAN, ReadStateError
from pybiotime.testing import FakeBioTime, RecordedRequest

BASE = "http://biotime.test"
DAY = datetime(2026, 10, 1)


def punch(fake: FakeBioTime, minute: int, *, uploaded: datetime | None = None) -> int:
    row = fake.add_transaction(
        emp_code="1001", punch_time=DAY + timedelta(minutes=minute), upload_time=uploaded
    )
    return int(row["id"])


def late_upload(fake: FakeBioTime) -> int:
    """An old punch from a device that was offline for months, uploaded now."""
    row = fake.add_transaction(
        emp_code="1002",
        punch_time=DAY - timedelta(days=120),
        upload_time=DAY + timedelta(hours=2),
    )
    return int(row["id"])


def arrive_mid_scan(fake: FakeBioTime, *minutes: int) -> list[int]:
    """Add punches right after the next arrival scan reads its first page."""
    added: list[int] = []

    def hook(request: RecordedRequest) -> None:
        if request.params.get("ordering") == "-upload_time" and "page" not in request.params:
            fake.after_request = None
            added.extend(punch(fake, minute) for minute in minutes)

    fake.after_request = hook
    return added


def client_for(fake: FakeBioTime) -> AsyncBioTimeClient:
    return AsyncBioTimeClient(
        BASE, auth=TokenAuth("api", "secret"), transport=fake.transport(), page_size=10
    )


@pytest.mark.anyio
async def test_first_run_returns_everything_then_only_new_punches() -> None:
    fake = FakeBioTime()
    first_ids = [punch(fake, m) for m in range(25)]

    async with client_for(fake) as client:
        first = await client.transactions.read_new()
        assert [t.id for t in first.transactions] == first_ids
        # The state survives a JSON round trip, as callers will store it.
        state = json.loads(json.dumps(first.state))

        again = await client.transactions.read_new(state)
        assert again.transactions == []

        new_ids = [punch(fake, 30 + m) for m in range(3)]
        third = await client.transactions.read_new(again.state)
        assert [t.id for t in third.transactions] == new_ids
    assert first.state["upload_order"] == "ok"


@pytest.mark.anyio
async def test_first_run_from_a_start_date() -> None:
    fake = FakeBioTime()
    for minute in range(10):
        punch(fake, minute)
    async with client_for(fake) as client:
        result = await client.transactions.read_new(start=DAY + timedelta(minutes=7))
    assert [t.punch_time.minute for t in result.transactions] == [7, 8, 9]


@pytest.mark.anyio
async def test_late_upload_of_an_old_punch_is_found() -> None:
    fake = FakeBioTime()
    for minute in range(5):
        punch(fake, minute)
    async with client_for(fake) as client:
        state = (await client.transactions.read_new()).state

        # A device that was offline for months uploads an old punch now.
        late = fake.add_transaction(
            emp_code="1002",
            punch_time=DAY - timedelta(days=120),
            upload_time=DAY + timedelta(minutes=10),
        )
        result = await client.transactions.read_new(state, lookback=timedelta(hours=1))
    assert [t.id for t in result.transactions] == [late["id"]]


@pytest.mark.anyio
async def test_lower_id_that_becomes_visible_later_is_found() -> None:
    fake = FakeBioTime()
    for minute in range(5):
        punch(fake, minute)
    # A slow database transaction commits id 3 after higher ids were visible.
    hidden = fake.transactions.pop(2)
    async with client_for(fake) as client:
        state = (await client.transactions.read_new()).state
        fake.transactions.append(hidden)
        result = await client.transactions.read_new(state)
    assert [t.id for t in result.transactions] == [hidden["id"]]


@pytest.mark.anyio
async def test_big_batch_with_one_upload_time_is_read_once() -> None:
    fake = FakeBioTime()
    punch(fake, 0)
    async with client_for(fake) as client:
        state = (await client.transactions.read_new()).state
        batch_time = DAY + timedelta(hours=1)
        batch = [punch(fake, m, uploaded=batch_time) for m in range(1, 151)]
        result = await client.transactions.read_new(state)
        again = await client.transactions.read_new(result.state)
    assert [t.id for t in result.transactions] == batch
    assert again.transactions == []


@pytest.mark.anyio
async def test_server_that_ignores_the_upload_sort_falls_back_to_the_window() -> None:
    fake = FakeBioTime()
    fake.honoured_orders = {"punch_time", "-punch_time"}
    now = datetime.now().replace(microsecond=0)
    for minute in range(25):
        fake.add_transaction(emp_code="1001", punch_time=now - timedelta(minutes=60 - minute))
    async with client_for(fake) as client:
        first = await client.transactions.read_new()
        recent = int(fake.add_transaction(emp_code="1001", punch_time=now)["id"])
        result = await client.transactions.read_new(first.state)
    assert first.state["upload_order"] == "unsupported"
    assert result.state["upload_order"] == "unsupported"
    assert [t.id for t in result.transactions] == [recent]
    sorts = {r.params.get("ordering") for r in fake.requests if r.path.endswith("transactions/")}
    assert sorts == {"-upload_time", "punch_time"}
    # Each run checks the sort again on one page, and stops there when it is ignored.
    checks = [r for r in fake.requests if r.params.get("ordering") == "-upload_time"]
    assert len(checks) == 2
    assert all("page" not in r.params for r in checks)


@pytest.mark.anyio
async def test_punches_arriving_mid_scan_do_not_disable_the_arrival_scan() -> None:
    fake = FakeBioTime()
    for minute in range(5):
        punch(fake, minute)
    async with client_for(fake) as client:
        state = (await client.transactions.read_new()).state
        # 25 arrivals take three pages of 10. Two more land while the scan is paging,
        # which pushes rows onto later pages: the next page starts newer than the last ended.
        busy = [punch(fake, minute) for minute in range(10, 35)]
        mid_scan = arrive_mid_scan(fake, 40, 41)
        result = await client.transactions.read_new(state)
        assert result.state["upload_order"] == "ok"
        assert [t.id for t in result.transactions] == busy + mid_scan

        late = late_upload(fake)
        after = await client.transactions.read_new(result.state, lookback=timedelta(hours=1))
    assert [t.id for t in after.transactions] == [late]


@pytest.mark.anyio
async def test_a_stored_unsupported_reading_is_checked_again() -> None:
    fake = FakeBioTime()
    fake.honoured_orders = {"punch_time", "-punch_time"}
    for minute in range(25):
        punch(fake, minute)
    async with client_for(fake) as client:
        first = await client.transactions.read_new()
        assert first.state["upload_order"] == "unsupported"
        # The server sorts by arrival again, for example after an upgrade. A state saved
        # by a wrong reading heals the same way.
        fake.honoured_orders.add("-upload_time")
        late = late_upload(fake)
        result = await client.transactions.read_new(first.state, lookback=timedelta(hours=1))
    assert result.state["upload_order"] == "ok"
    assert [t.id for t in result.transactions] == [late]


@pytest.mark.anyio
async def test_window_keeps_moving_when_the_server_stops_sorting_by_arrival() -> None:
    fake = FakeBioTime()
    punch(fake, 0)
    async with client_for(fake) as client:
        state = (await client.transactions.read_new()).state
        fake.honoured_orders = {"punch_time", "-punch_time"}
        starts: list[str] = []
        for day in (1, 2, 3):
            fake.add_transaction(emp_code="1001", punch_time=DAY + timedelta(days=day))
            state = (await client.transactions.read_new(state)).state
            window = [r for r in fake.requests if r.params.get("ordering") == "punch_time"]
            starts.append(window[-1].params["start_time"])
    # Anchored on the newest arrival seen, not on a time saved before the sort stopped.
    assert starts == ["2026-09-30 00:00:00", "2026-10-01 00:00:00", "2026-10-02 00:00:00"]
    assert state["max_upload_time"] == "2026-10-04 00:00:00"


@pytest.mark.anyio
async def test_restored_database_is_detected() -> None:
    fake = FakeBioTime()
    for minute in range(RECENT_ID_SPAN + 10):
        punch(fake, minute % 1000)
    async with client_for(fake) as client:
        state = (await client.transactions.read_new()).state
        fake.transactions.clear()
        fake._next_id = 1
        punch(fake, 0, uploaded=DAY + timedelta(days=30))
        with pytest.raises(ReadStateError, match="restored"):
            await client.transactions.read_new(state)


@pytest.mark.anyio
async def test_empty_server() -> None:
    fake = FakeBioTime()
    async with client_for(fake) as client:
        result = await client.transactions.read_new()
        punch(fake, 0)
        second = await client.transactions.read_new(result.state)
    assert result.transactions == []
    assert len(second.transactions) == 1
