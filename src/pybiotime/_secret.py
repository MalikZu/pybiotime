"""A string that keeps its value out of tracebacks.

Error reporters, Frappe's among them, can log every frame's local variables using
``repr()``. Credentials held as plain strings or dicts would land in those logs. A
`Secret` is a real ``str``, so httpx and ``json.dumps`` send its value unchanged, but
its ``repr()`` is redacted, and so is the ``repr()`` of any dict or list holding it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["Secret", "secret_token"]


class Secret(str):
    __slots__ = ()

    def __repr__(self) -> str:
        return "'<redacted>'"


def secret_token(body: Any) -> Any:
    """Return a login answer with its token wrapped in `Secret`."""
    if isinstance(body, dict) and isinstance(body.get("token"), str):
        return {**body, "token": Secret(body["token"])}
    return body
