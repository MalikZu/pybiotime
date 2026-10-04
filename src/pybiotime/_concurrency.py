"""Locks and sleep in async and sync flavours.

Code under `_async/` uses the async names. The unasync script swaps them for the sync
names when it generates `_sync/`.
"""

from __future__ import annotations

import asyncio
import threading
import time
from types import TracebackType


class AsyncLock:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> None:
        await self._lock.acquire()

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._lock.release()


class Lock:
    def __init__(self) -> None:
        self._lock = threading.Lock()

    def __enter__(self) -> None:
        self._lock.acquire()

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._lock.release()


async def async_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def sleep(seconds: float) -> None:
    time.sleep(seconds)
