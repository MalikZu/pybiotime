import json

import pytest

from pybiotime.incremental import RECENT_ID_SPAN, ReadState, ReadStateError


def test_round_trip() -> None:
    state = ReadState(
        max_id=50, recent_ids={48, 50}, max_upload_time="2026-10-01 08:00:00", upload_order="ok"
    )
    assert ReadState.from_dict(state.to_dict()) == state


def test_empty_state_is_a_first_run() -> None:
    assert ReadState.from_dict(None).is_first_run
    assert ReadState.from_dict({}).is_first_run


def test_unknown_version_is_refused() -> None:
    with pytest.raises(ReadStateError, match="version"):
        ReadState.from_dict({"version": 99})


def test_is_new() -> None:
    state = ReadState(max_id=10_000, recent_ids={9_999})
    assert state.is_new(10_001)
    assert state.is_new(9_998)
    assert not state.is_new(9_999)
    assert not state.is_new(10_000 - RECENT_ID_SPAN)
    assert ReadState().is_new(1)


def test_recent_ids_stay_bounded() -> None:
    state = ReadState()
    state.advance([], None)
    assert state.max_id is None
    state.recent_ids = set(range(1, 5_000))
    state.max_id = 4_999
    state.advance([], None)
    assert min(state.recent_ids) == 4_999 - RECENT_ID_SPAN + 1


def test_fingerprints_round_trip_beside_recent_ids() -> None:
    state = ReadState(max_id=50, recent_ids={48, 49, 50}, fingerprints={48: "aa", 50: "cc"})
    data = state.to_dict()
    assert data["recent_ids"] == [48, 49, 50]
    assert data["fingerprints"] == ["aa", None, "cc"]
    assert ReadState.from_dict(data).fingerprints == {48: "aa", 50: "cc"}


def test_fingerprints_that_do_not_line_up_are_ignored() -> None:
    data = ReadState(max_id=50, recent_ids={49, 50}).to_dict() | {"fingerprints": ["aa"]}
    assert ReadState.from_dict(data).fingerprints == {}


def test_a_full_state_stays_small() -> None:
    ids = set(range(10_000 - RECENT_ID_SPAN + 1, 10_001))
    state = ReadState(max_id=10_000, recent_ids=ids, fingerprints=dict.fromkeys(ids, "0a1b2c3d"))
    assert len(json.dumps(state.to_dict())) < 48_000
