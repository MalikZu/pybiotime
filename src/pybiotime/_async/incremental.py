from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from itertools import pairwise
from typing import TYPE_CHECKING, Any

from pybiotime.incremental import RECENT_ID_SPAN, ReadResult, ReadState, ReadStateError, naive
from pybiotime.models import Transaction

if TYPE_CHECKING:
    from pybiotime._async.resources import AsyncTransactions

#: Rows read on the first run to learn the newest arrival and check the upload-time sort.
_PROBE_ROWS = 50


async def read_new(
    transactions: AsyncTransactions,
    state: Mapping[str, Any] | None,
    *,
    start: datetime | None,
    lookback: timedelta,
    overlap: timedelta,
    page_size: int | None,
) -> ReadResult:
    current = ReadState.from_dict(state)
    found: dict[int, Transaction] = {}
    newest_upload: datetime | None = None

    if current.upload_order != "unsupported":
        if current.is_first_run:
            newest_upload = await _probe_upload_order(transactions, current)
        else:
            newest_upload = await _arrival_scan(transactions, current, found, overlap, page_size)

    if current.is_first_run:
        window_start = start
    else:
        anchor = newest_upload or current.newest_upload or _server_now(transactions)
        window_start = anchor - lookback
    async for punch in transactions.list(
        start=window_start, order_by="punch_time", page_size=page_size
    ):
        if current.is_new(punch.id):
            found[punch.id] = punch

    current.advance(found.values(), newest_upload)
    return ReadResult(
        transactions=sorted(found.values(), key=lambda t: t.id),
        state=current.to_dict(),
    )


async def _probe_upload_order(transactions: AsyncTransactions, state: ReadState) -> datetime | None:
    """Read the newest arrivals once: they anchor the next run and show if the sort works."""
    page = await transactions.list(order_by="-upload_time", page_size=_PROBE_ROWS).first_page()
    uploads = [naive(p.upload_time) for p in page.items if p.upload_time is not None]
    _record_order(state, uploads)
    return uploads[0] if uploads and state.upload_order != "unsupported" else None


async def _arrival_scan(
    transactions: AsyncTransactions,
    state: ReadState,
    found: dict[int, Transaction],
    overlap: timedelta,
    page_size: int | None,
) -> datetime | None:
    """Read arrivals newest first, back to the previous run's newest arrival minus `overlap`."""
    previous_newest = state.newest_upload
    threshold = previous_newest - overlap if previous_newest else None
    newest: datetime | None = None
    seen: list[datetime] = []

    async for punch in transactions.list(order_by="-upload_time", page_size=page_size):
        if punch.upload_time is None:
            continue
        uploaded = naive(punch.upload_time)
        seen.append(uploaded)
        if len(seen) > 1 and uploaded > seen[-2]:
            # The server ignored the sort. Rely on the punch-time window instead.
            state.upload_order = "unsupported"
            return None
        if newest is None:
            newest = uploaded
        if threshold is not None and uploaded < threshold:
            break
        if state.is_new(punch.id):
            found[punch.id] = punch
        elif (
            previous_newest is not None
            and state.max_id is not None
            and uploaded > previous_newest
            and punch.id <= state.max_id - RECENT_ID_SPAN
        ):
            raise ReadStateError(
                f"Transaction {punch.id} arrived after the last run but has a much lower id "
                f"than the {state.max_id} already seen. Was the database restored or reset? "
                "Start again without a state, from a known date."
            )

    _record_order(state, seen)
    return newest


def _record_order(state: ReadState, uploads: list[datetime]) -> None:
    pairs = list(pairwise(uploads))
    if any(later > earlier for earlier, later in pairs):
        state.upload_order = "unsupported"
    elif any(later < earlier for earlier, later in pairs):
        state.upload_order = "ok"


def _server_now(transactions: AsyncTransactions) -> datetime:
    """Best guess at the server's clock when it gave us nothing better."""
    timezone = transactions._client.timezone
    return naive(datetime.now(timezone)) if timezone else datetime.now()
