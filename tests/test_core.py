from datetime import datetime, timedelta, timezone

import pytest

from pybiotime._core import (
    PageGuard,
    RawPage,
    decode_response,
    format_datetime,
    merge_params,
    next_params,
    parse_page,
    resolve_timezone,
)
from pybiotime.errors import (
    APIError,
    AuthenticationError,
    BadRequestError,
    FaultPageError,
    LicenseError,
    NotFoundError,
    PaginationError,
    PermissionDeniedError,
    ServerError,
)

JSON = "application/json"
HTML = "text/html; charset=utf-8"


def decode(status: int, body: bytes, content_type: str = JSON) -> object:
    return decode_response(status, content_type, body, method="GET", path="/x/")


class TestDecodeResponse:
    def test_returns_json(self) -> None:
        assert decode(200, b'{"id": 1}') == {"id": 1}

    def test_empty_body_is_none(self) -> None:
        assert decode(204, b"") is None

    def test_html_with_200_is_a_fault_page(self) -> None:
        page = b"<!DOCTYPE HTML><html><title>Page not found</title></html>"
        with pytest.raises(FaultPageError) as caught:
            decode(200, page, HTML)
        assert caught.value.status_code == 200
        assert "Page not found" in caught.value.snippet

    def test_envelope_code_is_an_error(self) -> None:
        with pytest.raises(APIError) as caught:
            decode(200, b'{"code": 1, "msg": "No permission", "data": []}')
        assert caught.value.code == 1
        assert caught.value.detail == "No permission"

    def test_envelope_code_zero_is_fine(self) -> None:
        assert decode(200, b'{"code": 0, "msg": "", "data": []}') == {
            "code": 0,
            "msg": "",
            "data": [],
        }

    @pytest.mark.parametrize(
        ("status", "error"),
        [
            (401, AuthenticationError),
            (403, PermissionDeniedError),
            (404, NotFoundError),
            (405, APIError),
            (500, ServerError),
            (503, ServerError),
        ],
    )
    def test_status_maps_to_error(self, status: int, error: type[APIError]) -> None:
        with pytest.raises(error) as caught:
            decode(status, b'{"detail": "Nope."}')
        assert type(caught.value) is error
        assert caught.value.status_code == status
        assert caught.value.detail == "Nope."
        assert "Nope." in str(caught.value)

    def test_bad_request_keeps_field_errors(self) -> None:
        with pytest.raises(BadRequestError) as caught:
            decode(400, b'{"start_time": ["Enter a valid date/time."]}')
        assert caught.value.field_errors == {"start_time": ["Enter a valid date/time."]}

    def test_bad_request_non_field_errors_become_the_detail(self) -> None:
        body = b'{"non_field_errors": ["Unable to log in with provided credentials."]}'
        with pytest.raises(BadRequestError) as caught:
            decode(400, body)
        assert caught.value.detail == "Unable to log in with provided credentials."

    def test_403_mentioning_the_licence_is_a_license_error(self) -> None:
        with pytest.raises(LicenseError):
            decode(403, b'{"detail": "The license does not include the API module."}')

    def test_server_error_html_body_stays_out_of_the_message(self) -> None:
        with pytest.raises(ServerError) as caught:
            decode(500, b"<html>Traceback: secret stuff</html>", HTML)
        assert "secret" not in str(caught.value)
        assert caught.value.body is None

    def test_redirect_is_an_error(self) -> None:
        with pytest.raises(APIError, match="redirect"):
            decode(302, b"", HTML)


class TestParsePage:
    def test_reads_data(self) -> None:
        body = {
            "count": 3,
            "next": "http://10.0.0.5:8081/iclock/api/terminals/?page=2&page_size=2",
            "previous": None,
            "msg": "",
            "code": 0,
            "data": [{"id": 1}, {"id": 2}],
        }
        page = parse_page(body, method="GET", path="/x/")
        assert page.items == [{"id": 1}, {"id": 2}]
        assert page.count == 3
        assert page.next_params == {"page": "2", "page_size": "2"}

    def test_falls_back_to_results(self) -> None:
        page = parse_page({"count": 1, "results": [{"id": 1}]}, method="GET", path="/x/")
        assert page.items == [{"id": 1}]

    def test_empty_data_beside_results(self) -> None:
        body = {"count": 1, "data": [], "results": [{"id": 1}]}
        assert parse_page(body, method="GET", path="/x/").items == [{"id": 1}]

    def test_bare_list(self) -> None:
        page = parse_page([{"id": 1}], method="GET", path="/x/")
        assert page.items == [{"id": 1}]
        assert page.next_params is None

    def test_missing_list_is_an_error(self) -> None:
        with pytest.raises(PaginationError):
            parse_page({"count": 0}, method="GET", path="/x/")

    def test_next_link_keeps_only_the_query(self) -> None:
        url = "http://internal-host:8081/iclock/api/transactions/?page=3&page_size=2&emp_code=7"
        assert next_params(url) == {"page": "3", "page_size": "2", "emp_code": "7"}


class TestPageGuard:
    def page(self, ids: list[int], next_page: int | None) -> RawPage:
        params = {"page": str(next_page)} if next_page else None
        return RawPage(items=[{"id": i} for i in ids], count=None, next_params=params)

    def test_normal_pages_pass(self) -> None:
        guard = PageGuard()
        guard.check(self.page([1, 2], 2), path="/x/")
        guard.check(self.page([3, 4], 3), path="/x/")
        guard.check(self.page([5], None), path="/x/")

    def test_repeated_page(self) -> None:
        guard = PageGuard()
        guard.check(self.page([1, 2], 2), path="/x/")
        with pytest.raises(PaginationError, match="same page"):
            guard.check(self.page([1, 2], 3), path="/x/")

    def test_next_loop(self) -> None:
        guard = PageGuard()
        guard.check(self.page([1, 2], 2), path="/x/")
        with pytest.raises(PaginationError, match="already read"):
            guard.check(self.page([3, 4], 2), path="/x/")

    def test_empty_page_with_next(self) -> None:
        with pytest.raises(PaginationError, match="empty"):
            PageGuard().check(self.page([], 2), path="/x/")


class TestDatetimes:
    def test_naive_is_sent_as_is(self) -> None:
        assert format_datetime(datetime(2026, 10, 1, 8, 5, 9), None) == "2026-10-01 08:05:09"

    def test_aware_is_converted_to_server_time(self) -> None:
        dubai = resolve_timezone("Asia/Dubai")
        value = datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc)
        assert format_datetime(value, dubai) == "2026-10-01 08:00:00"

    def test_aware_without_server_timezone_is_refused(self) -> None:
        value = datetime(2026, 10, 1, tzinfo=timezone(timedelta(hours=4)))
        with pytest.raises(ValueError, match="timezone"):
            format_datetime(value, None)

    def test_unknown_timezone(self) -> None:
        with pytest.raises(ValueError, match="Unknown timezone") as caught:
            resolve_timezone("Mars/Olympus")
        # The name may be right on a system without timezone data, so say how to get it.
        assert "tzdata" in str(caught.value)


def test_merge_params_drops_none() -> None:
    assert merge_params({"a": 1, "b": None}, {"c": True}) == {"a": "1", "c": "true"}
