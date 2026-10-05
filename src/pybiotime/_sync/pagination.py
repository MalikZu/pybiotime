# Generated from src/pybiotime/_async/pagination.py by scripts/unasync.py. Do not edit.

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pybiotime._core import PageGuard, Params, RawPage, parse_page
from pybiotime.compat import page_params
from pybiotime.pagination import Page

if TYPE_CHECKING:
    from pybiotime._sync.client import BioTimeClient

T = TypeVar("T")

__all__ = ["Pager"]


class Pager(Generic[T]):
    """A lazy list of objects that fetches pages as you iterate.

    Iterate with ``for`` to get every object, or use `pages()`, `first()` and
    `count()`. Nothing is fetched until you do.
    """

    def __init__(
        self,
        client: BioTimeClient,
        path: str,
        params: Params,
        parse: Callable[[dict[str, Any]], T],
        page_size: int | None = None,
    ) -> None:
        self._client = client
        self._path = path
        self._params = params
        self._parse = parse
        self._page_size = page_size or client.page_size

    def __iter__(self) -> Iterator[T]:
        return self._items()

    def _items(self) -> Iterator[T]:
        for page in self.pages():
            for item in page.items:
                yield item

    def pages(self) -> Iterator[Page[T]]:
        """Yield each page in turn, following the server's next links."""
        params: Params = {**self._params, **page_params(self._page_size)}
        guard = PageGuard()
        while True:
            raw = parse_page(
                self._client._request("GET", self._path, params=params),
                method="GET",
                path=self._path,
            )
            guard.check(raw, path=self._path)
            yield Page(
                items=[self._parse(item) for item in raw.items],
                count=raw.count,
                has_next=raw.next_params is not None,
            )
            if raw.next_params is None:
                return
            params = raw.next_params

    def first_page(self) -> Page[T]:
        """Fetch only the first page."""
        params = {**self._params, **page_params(self._page_size)}
        raw = parse_page(
            self._client._request("GET", self._path, params=params),
            method="GET",
            path=self._path,
        )
        return Page(
            items=[self._parse(item) for item in raw.items],
            count=raw.count,
            has_next=raw.next_params is not None,
        )

    def first(self) -> T | None:
        """Fetch only the first matching object, or ``None`` if there is none."""
        raw = self._small_page()
        return self._parse(raw.items[0]) if raw.items else None

    def count(self) -> int:
        """Ask the server how many objects match, fetching a single object."""
        raw = self._small_page()
        return raw.count if raw.count is not None else len(raw.items)

    def _small_page(self) -> RawPage:
        params = {**self._params, **page_params(1)}
        body = self._client._request("GET", self._path, params=params)
        return parse_page(body, method="GET", path=self._path)
