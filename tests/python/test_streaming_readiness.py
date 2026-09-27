"""Tests for streaming readiness API (quantwave-h6xe)."""

import quantwave as qw


def test_track_streaming_explicit_warmup():
    cls = qw.streaming_class("rsi")
    wrapped = qw.track_streaming(cls(14), warmup_bars_count=3)
    for i in range(1, 4):
        wrapped.next(100.0 + i)
        assert wrapped.bars_consumed == i
        assert wrapped.is_ready == (i >= 3)
    assert wrapped.is_ready


def test_wrap_streaming_by_name():
    cls = qw.streaming_class("rsi")
    wrapped = qw.wrap_streaming(cls(14), name="rsi")
    for _ in range(13):
        wrapped.next(100.0)
        assert not wrapped.is_ready
    wrapped.next(100.0)
    assert wrapped.is_ready


# ---------------------------------------------------------------------------
# streaming_class(..., track_readiness=True) — quantwave-1jqv Part 2.
#
# Design choice: the zero-arg / positional call keeps returning the exact
# same raw PyO3 class as before (verified below), so existing callers and any
# isinstance()/type-identity checks on it are completely unaffected.
# track_readiness=True is the explicit opt-in that returns a factory whose
# instances come pre-wrapped with .is_ready/.bars_consumed.
# ---------------------------------------------------------------------------


def test_streaming_class_default_return_type_is_unchanged():
    """track_readiness defaults to False: identical to the old zero-arg call."""
    cls = qw.streaming_class("rsi")
    assert cls is qw.streaming_class("rsi", track_readiness=False)
    assert cls.__name__ in {"Rsi", "RSI"}
    inst = cls(14)
    assert not isinstance(inst, qw.StreamingWrapper)


def test_streaming_class_track_readiness_wraps_instances():
    tracked_cls = qw.streaming_class("rsi", track_readiness=True)
    assert tracked_cls is not qw.streaming_class("rsi")

    inst = tracked_cls(14)
    assert isinstance(inst, qw.StreamingWrapper)
    assert inst.bars_consumed == 0
    assert not inst.is_ready

    for i in range(13):
        inst.next(100.0 + i)
        assert not inst.is_ready
    inst.next(113.0)
    assert inst.is_ready
    assert inst.bars_consumed == 14


def test_streaming_class_track_readiness_next_still_works_unchanged():
    """.next() call sites written against the raw class keep working the
    same way through the tracked factory — it just gains readiness on top."""
    raw_cls = qw.streaming_class("rsi")
    tracked_cls = qw.streaming_class("rsi", track_readiness=True)

    raw = raw_cls(14)
    tracked = tracked_cls(14)

    import math

    raw_values = [raw.next(100.0 + i) for i in range(20)]
    tracked_values = [tracked.next(100.0 + i) for i in range(20)]

    assert len(raw_values) == len(tracked_values)
    for rv, tv in zip(raw_values, tracked_values):
        if isinstance(rv, float) and math.isnan(rv):
            assert isinstance(tv, float) and math.isnan(tv)
        else:
            assert rv == tv
    assert tracked.is_ready
    assert tracked.bars_consumed == 20


def test_streaming_class_unknown_name_returns_none_regardless_of_flag():
    assert qw.streaming_class("not_a_real_indicator_xyz") is None
    assert qw.streaming_class("not_a_real_indicator_xyz", track_readiness=True) is None