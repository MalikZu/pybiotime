"""Read-only checks against a real BioTime server. Skipped unless configured.

Set BIOTIME_URL, and either BIOTIME_TOKEN or BIOTIME_USERNAME and BIOTIME_PASSWORD.
Optionally set BIOTIME_TIMEZONE, and BIOTIME_VERSION to check version detection.
These tests never write to the server.
"""

import os
from collections.abc import Iterator
from datetime import timedelta

import pytest

from pybiotime import BioTimeClient, FaultPageError, TokenAuth
from pybiotime.auth import Auth

URL = os.environ.get("BIOTIME_URL")

pytestmark = pytest.mark.skipif(not URL, reason="BIOTIME_URL is not set")


def live_auth() -> Auth:
    token = os.environ.get("BIOTIME_TOKEN")
    if token:
        return TokenAuth(token=token)
    return TokenAuth(os.environ["BIOTIME_USERNAME"], os.environ["BIOTIME_PASSWORD"])


@pytest.fixture(scope="module")
def client() -> Iterator[BioTimeClient]:
    assert URL
    with BioTimeClient(
        URL, auth=live_auth(), timezone=os.environ.get("BIOTIME_TIMEZONE"), page_size=200
    ) as live:
        yield live


def test_terminals(client: BioTimeClient) -> None:
    terminals = list(client.terminals.list())
    assert len(terminals) == client.terminals.list().count()
    for terminal in terminals:
        assert client.terminals.get_by_sn(terminal.sn) == terminal


def test_transactions_page_without_gaps_or_duplicates(client: BioTimeClient) -> None:
    newest = client.transactions.list(order_by="-punch_time").first()
    if newest is None:
        pytest.skip("no transactions on this server")
    start = newest.punch_time - timedelta(days=30)
    pager = client.transactions.list(start=start, order_by="punch_time")
    punches = list(pager)
    assert len(punches) == pager.count()
    assert len({p.id for p in punches}) == len(punches)
    assert [p.punch_time for p in punches] == sorted(p.punch_time for p in punches)


def test_detail_matches_list(client: BioTimeClient) -> None:
    first = client.transactions.list().first()
    if first is None:
        pytest.skip("no transactions on this server")
    assert client.transactions.get(first.id).id == first.id


def test_read_new_twice(client: BioTimeClient) -> None:
    page = client.transactions.list(order_by="-upload_time", page_size=50).first_page()
    uploads = [p.upload_time for p in page.items if p.upload_time is not None]
    if not uploads:
        pytest.skip("no transactions on this server")
    first = client.transactions.read_new(start=page.items[0].punch_time - timedelta(days=2))
    second = client.transactions.read_new(first.state)
    seen = {t.id for t in first.transactions}
    assert not seen & {t.id for t in second.transactions}
    if len(set(uploads)) > 1 and uploads == sorted(uploads, reverse=True):
        # This server visibly sorts by arrival, so read_new must use that.
        assert first.state["upload_order"] == "ok"
        assert second.state["upload_order"] == "ok"


def test_unknown_path_is_a_fault_page(client: BioTimeClient) -> None:
    with pytest.raises(FaultPageError):
        client.request("GET", "/personnel/api/no-such-endpoint/")


def test_server_info(client: BioTimeClient) -> None:
    info = client.server_info()
    assert info.version is not None
    expected = os.environ.get("BIOTIME_VERSION")
    if expected:
        assert info.version == expected
