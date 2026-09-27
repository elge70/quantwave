"""Tests for Rust -> Python metadata codegen (quantwave-iqq7)."""

import pytest

import quantwave as qw
from quantwave import _metadata_generated as _gen


def test_generated_metadata_registry_populated():
    names = qw.indicators()
    assert len(names) >= 200, f"expected 200+ indicators from Rust codegen, got {len(names)}"


def test_hand_override_wins_for_rsi():
    meta = qw.metadata("rsi")
    assert meta is not None
    assert meta.warmup_bars == 14
    assert "close" in meta.data_inputs


def test_sr_monitor_from_overlay():
    meta = qw.metadata("sr_monitor")
    assert meta is not None
    assert meta.warmup_bars == 0
    assert "interaction_count" in meta.outputs


# Slugs where the real PyO3 streaming-class constructor's param names/arity
# diverge from the Rust IndicatorMetadata registry's `params` list (quantwave-lt3t
# item #2). scripts/metadata_overlay.json corrects `optional_params` for these via
# `optional_params_replace: true`; this test is the tripwire that catches any
# future regression (e.g. someone editing the overlay and re-introducing the old,
# mismatched registry param names).
STREAMING_CTOR_ROUNDTRIP_SLUGS = [
    "hamming_filter",
    "hann_filter",
    "hurst_exponent",
    "ichimoku",
    "kalman_filter",
    "mesa_stochastic",
    "my_rsi",
    "oc_price_rsi",
    "noise_elimination",
    "projected_moving_average",
    "recursive_median",
    "reversion_index",
    "undersampled_double_ma",
    "keltner",
    "kama",
]


@pytest.mark.parametrize("slug", STREAMING_CTOR_ROUNDTRIP_SLUGS)
def test_streaming_class_constructs_from_declared_optional_params(slug):
    """cls(**metadata.optional_params) must actually construct the real streaming class."""
    cls = qw.streaming_class(slug)
    assert cls is not None, f"no streaming class registered for {slug!r}"
    optional_params = _gen.GENERATED_ENTRIES[slug]["optional_params"]
    cls(**optional_params)  # raises TypeError on any name/arity mismatch


def test_swiss_army_knife_mode_requires_enum_not_declared_string_default():
    """
    swiss_army_knife's real ctor is SwissArmyKnife(mode: SwissMode, period, delta).
    `mode` is a #[pyclass(eq, eq_int)] enum, not a string -- the plain-JSON default
    the metadata schema stores ("BandPass") cannot be forwarded directly to the
    constructor. This is a documented schema limitation (see the swiss_army_knife
    `_note` in scripts/metadata_overlay.json), not something optional_params can
    fix, so this test locks in the *documented* failure mode instead of a silent
    round-trip.
    """
    cls = qw.streaming_class("swiss_army_knife")
    optional_params = _gen.GENERATED_ENTRIES["swiss_army_knife"]["optional_params"]
    with pytest.raises(TypeError):
        cls(**optional_params)
    # The real fix: pass the actual enum member.
    cls(mode=qw.SwissMode.BandPass, period=20, delta=0.1)