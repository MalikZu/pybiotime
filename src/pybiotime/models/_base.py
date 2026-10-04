"""Shared model base and lenient field types.

BioTime is loose with types across versions: numbers arrive as strings, empty strings
stand in for null, and booleans come as 0/1, "Yes"/"No" or "-". These types accept all
of that and give one clean Python type.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, ValidationInfo


class BioTimeModel(BaseModel):
    """Base for every model. Fields the model does not declare are kept in `extra`."""

    model_config = ConfigDict(extra="allow", frozen=True)

    @property
    def extra(self) -> dict[str, Any]:
        """Fields the server sent that this model does not declare, such as custom attributes."""
        return dict(self.model_extra or {})


def _blank_to_none(value: Any) -> Any:
    if isinstance(value, str) and not value.strip():
        return None
    return value


def _to_str(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return value


_TRUE = {"1", "true", "yes", "y"}
_FALSE = {"0", "false", "no", "n"}


def _to_bool(value: Any) -> bool | None:
    if isinstance(value, bool) or value is None:
        return value
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    # "-", "255" and anything else unknown means "not recorded".
    return None


def _attach_timezone(value: datetime | None, info: ValidationInfo) -> datetime | None:
    timezone = (info.context or {}).get("timezone")
    if value is not None and timezone is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value


#: An integer that may arrive as a string, or as "" for none.
LenientInt = Annotated[int | None, BeforeValidator(_blank_to_none)]

#: A float that may arrive as a string, or as "" for none.
LenientFloat = Annotated[float | None, BeforeValidator(_blank_to_none)]

#: A boolean from 0/1, "Yes"/"No", true/false. Unknown markers such as "-" become None.
LenientBool = Annotated[bool | None, BeforeValidator(_to_bool)]

#: A code that may arrive as a number or a string. Kept as a string.
Code = Annotated[str, BeforeValidator(_to_str)]

#: A naive server-local timestamp. Gets the client's timezone when one is configured.
BioTimeDateTime = Annotated[datetime, AfterValidator(_attach_timezone)]

#: An optional `BioTimeDateTime`; "" counts as none.
OptionalDateTime = Annotated[
    datetime | None, BeforeValidator(_blank_to_none), AfterValidator(_attach_timezone)
]
