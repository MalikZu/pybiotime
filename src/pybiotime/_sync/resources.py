# Generated from src/pybiotime/_async/resources.py by scripts/unasync.py. Do not edit.

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from pybiotime._core import build_model, format_datetime, merge_params
from pybiotime._sync.pagination import Pager
from pybiotime.models import Terminal, Transaction
from pybiotime.models.transaction import TransactionOrder

if TYPE_CHECKING:
    from pybiotime._sync.client import BioTimeClient

__all__ = ["Terminals", "Transactions"]


class Terminals:
    """Devices: ``/iclock/api/terminals/``. Read-only, since devices register themselves."""

    path = "/iclock/api/terminals/"

    def __init__(self, client: BioTimeClient) -> None:
        self._client = client

    def list(
        self,
        *,
        sn: str | None = None,
        alias: str | None = None,
        area: int | None = None,
        page_size: int | None = None,
    ) -> Pager[Terminal]:
        """List devices. Text filters may match partially; `get_by_sn` matches exactly."""
        params = merge_params({"sn": sn, "alias": alias, "area": area})
        return Pager(self._client, self.path, params, self._parse, page_size)

    def get(self, terminal_id: int) -> Terminal:
        """Fetch one device by its id. Raises `NotFoundError` if there is none."""
        path = f"{self.path}{terminal_id}/"
        return build_model(
            Terminal,
            self._client._request("GET", path),
            timezone=self._client.timezone,
            path=path,
        )

    def get_by_sn(self, sn: str) -> Terminal | None:
        """Fetch the device with exactly this serial number, or ``None``."""
        for terminal in self.list(sn=sn):
            if terminal.sn == sn:
                return terminal
        return None

    def _parse(self, item: dict[str, Any]) -> Terminal:
        return build_model(Terminal, item, timezone=self._client.timezone, path=self.path)


class Transactions:
    """Punches: ``/iclock/api/transactions/``. Read-only."""

    path = "/iclock/api/transactions/"

    def __init__(self, client: BioTimeClient) -> None:
        self._client = client

    def list(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        emp_code: str | None = None,
        terminal_sn: str | None = None,
        order_by: TransactionOrder | None = None,
        page_size: int | None = None,
    ) -> Pager[Transaction]:
        """List punches.

        `start` and `end` filter on punch time, not on when the server received the punch.
        A device that was offline can upload old punches much later, so a time window alone
        misses them. Use `read_new` to collect new punches without gaps.
        """
        timezone = self._client.timezone
        params = merge_params(
            {
                "start_time": format_datetime(start, timezone) if start is not None else None,
                "end_time": format_datetime(end, timezone) if end is not None else None,
                "emp_code": emp_code,
                "terminal_sn": terminal_sn,
                "ordering": order_by,
            }
        )
        return Pager(self._client, self.path, params, self._parse, page_size)

    def get(self, transaction_id: int) -> Transaction:
        """Fetch one punch by its id. Raises `NotFoundError` if there is none."""
        path = f"{self.path}{transaction_id}/"
        return build_model(
            Transaction,
            self._client._request("GET", path),
            timezone=self._client.timezone,
            path=path,
        )

    def _parse(self, item: dict[str, Any]) -> Transaction:
        return build_model(Transaction, item, timezone=self._client.timezone, path=self.path)
