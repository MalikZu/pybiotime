from __future__ import annotations

from typing import Literal

from pybiotime.models._base import (
    BioTimeDateTime,
    BioTimeModel,
    Code,
    LenientBool,
    LenientFloat,
    LenientInt,
    OptionalDateTime,
)

__all__ = ["Transaction", "TransactionOrder"]

#: Sort orders the server honours for transactions. It silently ignores any other value,
#: so the choice is closed. Without one, BioTime 9.5 returns ascending ids.
TransactionOrder = Literal["punch_time", "-punch_time", "upload_time", "-upload_time"]


class Transaction(BioTimeModel):
    """One punch recorded by a device.

    Use `emp_code` and `terminal_sn` to find the person and the device. The `emp` and
    `terminal` ids are usually null.
    """

    id: int
    emp_code: str
    #: When the person punched, in server-local time.
    punch_time: BioTimeDateTime
    #: Raw code; compare with `pybiotime.PunchState`.
    punch_state: Code
    punch_state_display: str | None = None
    #: Raw code; compare with `pybiotime.VerifyType`.
    verify_type: LenientInt = None
    verify_type_display: str | None = None
    work_code: str | None = None
    terminal_sn: str | None = None
    terminal_alias: str | None = None
    area_alias: str | None = None
    #: When the server received the punch. Much later than `punch_time` if the device was offline.
    upload_time: OptionalDateTime = None
    first_name: str | None = None
    last_name: str | None = None
    emp: LenientInt = None
    terminal: LenientInt = None
    temperature: LenientFloat = None
    is_mask: LenientBool = None
    gps_location: str | None = None
    longitude: LenientFloat = None
    latitude: LenientFloat = None
