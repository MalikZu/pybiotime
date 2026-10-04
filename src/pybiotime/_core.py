"""Request and response handling with no network code.

The sync and async clients share these functions, so both behave the same.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, tzinfo
from typing import Any, TypeVar
from urllib.parse import parse_qsl, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ValidationError

from pybiotime.errors import (
    APIError,
    AuthenticationError,
    BadRequestError,
    FaultPageError,
    LicenseError,
    NotFoundError,
    PaginationError,
    PermissionDeniedError,
    ResponseShapeError,
    ServerError,
)

#: Format of every timestamp BioTime sends and accepts. It carries no timezone.
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

_SNIPPET_LENGTH = 200

Params = dict[str, str]


def resolve_timezone(value: str | tzinfo | None) -> tzinfo | None:
    """Turn a timezone name such as ``"Asia/Dubai"`` into a `tzinfo`."""
    if value is None or isinstance(value, tzinfo):
        return value
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        raise ValueError(
            f"Unknown timezone {value!r}. Use an IANA name such as 'Asia/Dubai'. "
            "If the name is right, this system has no timezone data: install the "
            "'tzdata' package."
        ) from None


def format_datetime(value: datetime, timezone: tzinfo | None) -> str:
    """Format a datetime for a BioTime filter.

    BioTime compares naive server-local times. An aware value is first converted to the
    server's timezone, which the client must know.
    """
    if value.tzinfo is not None:
        if timezone is None:
            raise ValueError(
                "This datetime has a timezone, but the client does not know the server's. "
                "Pass timezone= to the client, or use a naive datetime in server time."
            )
        value = value.astimezone(timezone).replace(tzinfo=None)
    return value.strftime(DATETIME_FORMAT)


def decode_response(
    status_code: int, content_type: str, content: bytes, *, method: str, path: str
) -> Any:
    """Decode a response body, or raise the matching error."""
    body = _try_json(content)

    if status_code >= 300:
        raise error_for_status(
            status_code, body, content=content, content_type=content_type, method=method, path=path
        )
    if not content.strip():
        return None
    if body is _NOT_JSON:
        kind = content_type or "no content type"
        raise FaultPageError(
            f"{method} {path} returned a non-JSON page (HTTP {status_code}, {kind}). "
            "The path may be wrong, or the server may be starting or failing.",
            status_code=status_code,
            content_type=content_type,
            snippet=_snippet(content),
        )
    if isinstance(body, dict):
        code = body.get("code")
        if isinstance(code, int) and code != 0:
            message = body.get("msg") or "no message"
            raise APIError(
                f"{method} {path} failed with code {code}: {message}",
                status_code=status_code,
                method=method,
                path=path,
                detail=message if isinstance(message, str) else None,
                body=body,
                code=code,
            )
    return body


def error_for_status(
    status_code: int,
    body: Any,
    *,
    content: bytes,
    content_type: str,
    method: str,
    path: str,
) -> APIError:
    """Build the exception for an HTTP error response."""
    if body is _NOT_JSON:
        body = None
    detail = _detail(body)
    message = f"{method} {path} failed with HTTP {status_code}"
    if detail:
        message += f": {detail}"
    kwargs: dict[str, Any] = {
        "status_code": status_code,
        "method": method,
        "path": path,
        "detail": detail,
        "body": body,
    }

    if status_code == 400:
        return BadRequestError(message, field_errors=_field_errors(body), **kwargs)
    if status_code == 401:
        return AuthenticationError(message, **kwargs)
    if status_code == 403:
        # The licence gate has no documented body, so look for the word in what we got.
        text = (detail or "") + " " + (_snippet(content) if body is None else "")
        if "licen" in text.lower():
            return LicenseError(message, **kwargs)
        return PermissionDeniedError(message, **kwargs)
    if status_code == 404:
        return NotFoundError(message, **kwargs)
    if status_code >= 500:
        # Error pages can hold tracebacks, so the body stays out of the message.
        return ServerError(message, **kwargs)
    if 300 <= status_code < 400:
        message = f"{method} {path} was redirected (HTTP {status_code}); redirects are not followed"
    return APIError(message, **kwargs)


@dataclass(frozen=True)
class RawPage:
    """One page of a list endpoint, before its items are turned into models."""

    items: list[dict[str, Any]]
    count: int | None
    next_params: Params | None


def parse_page(body: Any, *, method: str, path: str) -> RawPage:
    """Read the list envelope: ``{count, next, previous, msg, code, data}``.

    Items are under ``data``; some servers use DRF's ``results`` instead.
    """
    if isinstance(body, list):
        return RawPage(items=_items(body, path), count=len(body), next_params=None)
    if not isinstance(body, dict):
        raise PaginationError(f"{method} {path} did not return a list envelope")

    items = body.get("data")
    if not isinstance(items, list) or (not items and body.get("results")):
        items = body.get("results")
    if not isinstance(items, list):
        raise PaginationError(f"{method} {path} returned an envelope without a data list")

    count = body.get("count")
    next_url = body.get("next")
    return RawPage(
        items=_items(items, path),
        count=count if isinstance(count, int) else None,
        next_params=next_params(next_url) if isinstance(next_url, str) and next_url else None,
    )


def next_params(url: str) -> Params:
    """Return the query parameters of a ``next`` link.

    Only the query string is used. BioTime builds the link from its own idea of its
    address, which is often an internal host the caller cannot reach.
    """
    return dict(parse_qsl(urlsplit(url).query, keep_blank_values=True))


class PageGuard:
    """Stop pagination that would loop forever or silently skip data."""

    def __init__(self) -> None:
        self._queries: set[tuple[tuple[str, str], ...]] = set()
        self._pages: set[tuple[Any, ...]] = set()

    def check(self, page: RawPage, *, path: str) -> None:
        if page.next_params is not None:
            if not page.items:
                raise PaginationError(f"{path}: an empty page still points to a next page")
            query = tuple(sorted(page.next_params.items()))
            if query in self._queries:
                raise PaginationError(f"{path}: the next link points to a page already read")
            self._queries.add(query)

        if page.items:
            fingerprint = tuple(_identity(item) for item in page.items)
            if fingerprint in self._pages:
                raise PaginationError(f"{path}: the server returned the same page twice")
            self._pages.add(fingerprint)


def merge_params(*parts: Mapping[str, object | None]) -> Params:
    """Merge query parameters, dropping ``None`` values."""
    merged: Params = {}
    for part in parts:
        for key, value in part.items():
            if value is not None:
                merged[key] = _param_value(value)
    return merged


def _param_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


_NOT_JSON = object()


def _try_json(content: bytes) -> Any:
    if not content.strip():
        return None
    try:
        return json.loads(content)
    except ValueError:
        return _NOT_JSON


def _detail(body: Any) -> str | None:
    if isinstance(body, dict):
        for key in ("detail", "msg", "message", "error"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
        errors = body.get("non_field_errors")
        if isinstance(errors, list) and errors:
            return "; ".join(str(error) for error in errors)
    if isinstance(body, str) and body:
        return body
    return None


def _field_errors(body: Any) -> dict[str, list[str]]:
    if not isinstance(body, dict):
        return {}
    errors: dict[str, list[str]] = {}
    for key, value in body.items():
        if key in ("detail", "code", "msg"):
            continue
        if isinstance(value, list):
            errors[key] = [str(item) for item in value]
        elif isinstance(value, str):
            errors[key] = [value]
    return errors


def _items(items: list[Any], path: str) -> list[dict[str, Any]]:
    for item in items:
        if not isinstance(item, dict):
            raise PaginationError(f"{path}: a list item is not an object")
    return items


def _identity(item: dict[str, Any]) -> Any:
    if "id" in item:
        return item["id"]
    return json.dumps(item, sort_keys=True, default=str)


def _snippet(content: bytes) -> str:
    return content[:_SNIPPET_LENGTH].decode("utf-8", "replace").strip()


M = TypeVar("M", bound=BaseModel)


def build_model(model: type[M], data: Any, *, timezone: tzinfo | None, path: str) -> M:
    """Validate one object from the server into `model`."""
    try:
        return model.model_validate(data, context={"timezone": timezone})
    except ValidationError as exc:
        raise ResponseShapeError(
            f"{path}: unexpected {model.__name__} data: {exc.error_count()} problem(s), "
            f"first: {exc.errors()[0]['loc']} {exc.errors()[0]['msg']}"
        ) from exc
