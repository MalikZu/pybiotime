from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pybiotime._core import PageGuard, Params, RawPage, parse_page
from pybiotime.pagination import Page

if TYPE_CHECKING:
    from pybiotime._async.client import AsyncBioTimeClient

T = TypeVar("T")

__all__ = ["AsyncPager"]


class AsyncPager(Generic[T]):
    """A lazy list of objects that fetches pages as you iterate.

    Iterate with ``async for`` to get every object, or use `pages()`, `first()` and
    `count()`. Nothing is fetched until you do.
    """

    def __init__(
        self,
        client: AsyncBioTimeClient,
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

    def __aiter__(self) -> AsyncIterator[T]:
        return self._items()

    async def _items(self) -> AsyncIterator[T]:
        async for page in self.pages():
            for item in page.items:
                yield item

    async def pages(self) -> AsyncIterator[Page[T]]:
        """Yield each page in turn, following the server's next links."""
        params: Params = {**self._params, "page_size": str(self._page_size)}
        guard = PageGuard()
        while True:
            raw = parse_page(
                await self._client._request("GET", self._path, params=params),
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

    async def first(self) -> T | None:
        """Fetch only the first matching object, or ``None`` if there is none."""
        raw = await self._small_page()
        return self._parse(raw.items[0]) if raw.items else None

    async def count(self) -> int:
        """Ask the server how many objects match, fetching a single object."""
        raw = await self._small_page()
        return raw.count if raw.count is not None else len(raw.items)

    async def _small_page(self) -> RawPage:
        params = {**self._params, "page_size": "1"}
        body = await self._client._request("GET", self._path, params=params)
        return parse_page(body, method="GET", path=self._path)
