"""Pages of list results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")

__all__ = ["Page"]


@dataclass(frozen=True)
class Page(Generic[T]):
    """One page of a list, as the server returned it."""

    items: list[T]
    #: Total number of matching objects, as the server counted them.
    count: int | None
    #: Whether the server says another page follows.
    has_next: bool
