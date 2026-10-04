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
