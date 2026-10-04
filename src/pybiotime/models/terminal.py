from __future__ import annotations

from pybiotime.models._base import (
    BioTimeModel,
    LenientBool,
    LenientInt,
    OptionalDateTime,
)
from pybiotime.models.refs import AreaRef

__all__ = ["Terminal"]


class Terminal(BioTimeModel):
    """A device that registered itself with the server.

    `sn` (the serial number) is the stable identifier. Transactions refer to devices by it.
    """

    id: int
    sn: str
    alias: str | None = None
    ip_address: str | None = None
    terminal_name: str | None = None
    fw_ver: str | None = None
    push_ver: str | None = None
    #: Device status code. Sent as a number or a string depending on the version.
    state: LenientInt = None
    #: The device's timezone setting, as BioTime stores it.
    terminal_tz: LenientInt = None
    area: AreaRef | None = None
    area_name: str | None = None
    last_activity: OptionalDateTime = None
    #: Kept as sent: its format is not documented.
    push_time: str | None = None
    #: Times of day the device uploads, separated by semicolons, for example "00:00;14:05".
    transfer_time: str | None = None
    #: Minutes between uploads.
    transfer_interval: LenientInt = None
    #: Whether punches from this device count as attendance.
    is_attendance: LenientBool = None
    user_count: LenientInt = None
    fp_count: LenientInt = None
    face_count: LenientInt = None
    palm_count: LenientInt = None
    transaction_count: LenientInt = None
