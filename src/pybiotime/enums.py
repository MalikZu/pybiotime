"""Known codes for punch states and verification types.

BioTime sends these as raw codes, and devices can send codes not listed here, so model
fields keep the raw value. Compare against these members, for example
``punch.punch_state == PunchState.CHECK_IN``.
"""

from __future__ import annotations

from enum import Enum, IntEnum

__all__ = ["PunchState", "VerifyType"]


class PunchState(str, Enum):
    """What the person chose on the device when punching. Sent as a string."""

    CHECK_IN = "0"
    CHECK_OUT = "1"
    BREAK_OUT = "2"
    BREAK_IN = "3"
    OVERTIME_IN = "4"
    OVERTIME_OUT = "5"
    #: The device does not track punch states.
    UNKNOWN = "255"


class VerifyType(IntEnum):
    """How the person proved who they are. Firmware may send other values."""

    ANY = 0
    FINGERPRINT = 1
    CARD = 4
    FACE = 15
    PALM = 25
