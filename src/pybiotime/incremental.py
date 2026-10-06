"""State for reading new punches without gaps. See `BioTimeClient.transactions.read_new`.

Why this is hard: BioTime can only filter punches by punch time, and a device that was
offline uploads old punches much later. A punch-time window alone misses those. Ids are
assigned on arrival, so "new" means "an id we have not seen", and the server's
upload-time sort finds recent arrivals quickly. The state below remembers enough of what
was seen to tell new from old across runs, and stays small enough to store anywhere.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from itertools import pairwise
from typing import Any, Literal

from pybiotime._core import DATETIME_FORMAT
from pybiotime.errors import BioTimeError
from pybiotime.models import Transaction

__all__ = ["ReadResult", "ReadState", "ReadStateError"]

#: Ids this far below the highest seen id are still checked one by one, because a slow
#: database transaction can make a lower id visible after a higher one.
RECENT_ID_SPAN = 2000

UploadOrder = Literal["unknown", "ok", "unsupported"]

_STATE_VERSION = 1


class ReadStateError(BioTimeError):
    """The stored state does not fit the server, for example after a database restore."""


@dataclass
class ReadState:
    """What earlier runs saw. Store `to_dict()` and pass it to the next run."""

    max_id: int | None = None
    #: Ids above ``max_id - RECENT_ID_SPAN`` that were already returned.
    recent_ids: set[int] = field(default_factory=set)
    #: A short fingerprint of the punch behind each recent id, where known. A known id
    #: that comes back as a different punch means the database was restored.
    fingerprints: dict[int, str] = field(default_factory=dict)
    #: Newest upload time seen, in server time, as BioTime formats it.
    max_upload_time: str | None = None
    #: Whether the server honoured the upload-time sort the last time a page could tell.
    #: For information only: every run checks again, so one wrong reading never sticks.
    upload_order: UploadOrder = "unknown"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> ReadState:
        if not data:
            return cls()
        if data.get("version") != _STATE_VERSION:
            raise ReadStateError(f"Unsupported state version: {data.get('version')!r}")
        order = data.get("upload_order", "unknown")
        recent = sorted(set(data.get("recent_ids", ())))
        # Stored in the order of recent_ids, so ids are not written twice. States from
        # before fingerprints have none: those ids are not checked until they fill.
        stored = data.get("fingerprints")
        fingerprints: dict[int, str] = {}
        if isinstance(stored, list) and len(stored) == len(recent):
            fingerprints = {i: f for i, f in zip(recent, stored, strict=True) if isinstance(f, str)}
        return cls(
            max_id=data.get("max_id"),
            recent_ids=set(recent),
            fingerprints=fingerprints,
            max_upload_time=data.get("max_upload_time"),
            upload_order=order if order in ("unknown", "ok", "unsupported") else "unknown",
        )

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serialisable copy."""
        recent = sorted(self.recent_ids)
        return {
            "version": _STATE_VERSION,
            "max_id": self.max_id,
            "recent_ids": recent,
            "fingerprints": [self.fingerprints.get(i) for i in recent],
            "max_upload_time": self.max_upload_time,
            "upload_order": self.upload_order,
        }

    @property
    def is_first_run(self) -> bool:
        return self.max_id is None

    def is_new(self, transaction_id: int) -> bool:
        if self.max_id is None or transaction_id > self.max_id:
            return True
        return (
            transaction_id > self.max_id - RECENT_ID_SPAN and transaction_id not in self.recent_ids
        )

    def is_new_punch(self, punch: Transaction) -> bool:
        """Whether `punch` was not returned before. Raises if its id now holds another punch.

        BioTime gives a restored database's new punches the ids it had already used. Within
        the recent span, their content then differs from what was returned under that id.
        """
        if self.is_new(punch.id):
            return True
        known = self.fingerprints.get(punch.id)
        if known is None:
            # A state from before fingerprints: learn this one, check it from now on.
            self.fingerprints[punch.id] = fingerprint(punch)
        elif known != fingerprint(punch):
            raise ReadStateError(
                f"BioTime now returns a different punch under id {punch.id} than it did "
                "before. Was the database restored or reset? Start again without a state, "
                "from a known date."
            )
        return False

    @property
    def newest_upload(self) -> datetime | None:
        if self.max_upload_time is None:
            return None
        return datetime.strptime(self.max_upload_time, DATETIME_FORMAT)

    def advance(self, transactions: Iterable[Transaction], newest_upload: datetime | None) -> None:
        """Record what this run returned."""
        punches = list(transactions)
        ids = {t.id for t in punches}
        if ids:
            self.max_id = max(ids if self.max_id is None else ids | {self.max_id})
        self.fingerprints.update((t.id, fingerprint(t)) for t in punches)
        if self.max_id is not None:
            floor = self.max_id - RECENT_ID_SPAN
            self.recent_ids = {i for i in self.recent_ids | ids if i > floor}
            self.fingerprints = {i: f for i, f in self.fingerprints.items() if i in self.recent_ids}
        if newest_upload is not None:
            text = naive(newest_upload).strftime(DATETIME_FORMAT)
            if self.max_upload_time is None or text > self.max_upload_time:
                self.max_upload_time = text


@dataclass(frozen=True)
class ReadResult:
    """New punches, oldest id first, and the state to store for the next run."""

    transactions: list[Transaction]
    state: dict[str, Any]


def fingerprint(punch: Transaction) -> str:
    """Eight hex characters for who punched, when and where. Short, to keep the state small."""
    text = "|".join(
        (
            punch.emp_code,
            naive(punch.punch_time).strftime(DATETIME_FORMAT),
            punch.terminal_sn or "",
        )
    )
    return hashlib.blake2b(text.encode(), digest_size=4).hexdigest()


def naive(value: datetime) -> datetime:
    """Drop the timezone the client may have attached. Server times are compared as sent."""
    return value.replace(tzinfo=None)


def latest(*values: datetime | None) -> datetime | None:
    """The latest of the given times, ignoring ``None``."""
    present = [value for value in values if value is not None]
    return max(present) if present else None


def page_order(uploads: Sequence[datetime]) -> UploadOrder:
    """How one page of a newest-arrival-first listing is really ordered.

    One page is one database query, so an upload time that rises inside it proves the
    server ignored the sort: ``"unsupported"``. Only falls means ``"ok"``. A page whose
    rows all share one upload time cannot tell: ``"unknown"``.

    Never compare across pages. Punches that arrive while a client pages push rows onto
    later pages, so the next page can start newer than the previous one ended.
    """
    pairs = list(pairwise(uploads))
    if any(later > earlier for earlier, later in pairs):
        return "unsupported"
    if any(later < earlier for earlier, later in pairs):
        return "ok"
    return "unknown"
