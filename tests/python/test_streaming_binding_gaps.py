"""Streaming-class PyO3-binding gap fixes (quantwave-lt3t).

Before this fix, `quantwave.streaming_class(name)` silently returned `None`
for 95 indicators (61 candlestick patterns + 34 others) even though most of
them already had a real, native `Next<T>` streaming implementation in
quantwave-core -- the PyO3 binding was simply never wired up.

This file verifies:
  1. `streaming_class()` now returns a real class for every indicator we
     wired up (not None).
  2. Calling `.next(...)` bar-by-bar on that streaming class produces output
     bit-identical to the batch `_quantwave.<fn>()` call over the same data
     (the batch/streaming parity guarantee the library advertises).
  3. The small number of indicators we deliberately left unfixed
     (hmm_forecast, lambda_hmm, sr_monitor) still return None, so a
     regression there is caught too -- see
     docs/generated/streaming_gap_findings.md for why.
"""

from __future__ import annotations

import math
import random

import pytest

import quantwave as qw
from quantwave import _quantwave

random.seed(20260927)
N = 60
CLOSES = [100.0 + random.gauss(0, 1) for _ in range(N)]
HIGHS = [c + abs(random.gauss(0, 0.5)) for c in CLOSES]
LOWS = [c - abs(random.gauss(0, 0.5)) for c in CLOSES]
OPENS = [c + random.gauss(0, 0.3) for c in CLOSES]
VOLUMES = [1000.0 + random.gauss(0, 50) for _ in CLOSES]


def _assert_series_equal(name: str, batch_out, stream_out, tol: float = 1e-9) -> None:
    assert len(batch_out) == len(stream_out), name
    for i, (b, s) in enumerate(zip(batch_out, stream_out)):
        if isinstance(b, float) and math.isnan(b):
            assert isinstance(s, float) and math.isnan(s), f"{name}[{i}]: {b} vs {s}"
            continue
        assert abs(b - s) <= tol, f"{name}[{i}]: batch={b} stream={s}"


# ---------------------------------------------------------------------------
# 1-series (close-only) indicators
# ---------------------------------------------------------------------------

ONE_IN_CASES = [
    ("apo", "apo", dict(fastperiod=12, slowperiod=26)),
    ("ppo", "ppo", dict(fastperiod=12, slowperiod=26)),
    ("cmo", "cmo", dict(timeperiod=14)),
    ("trix", "trix", dict(timeperiod=14)),
    ("stddev", "stddev", dict(timeperiod=14, nbdev=1.0)),
    ("trima", "trima", dict(timeperiod=14)),
    ("linreg", "linreg", dict(timeperiod=14)),
    ("zlema", "zlema", dict(period=14)),
    ("reverse_ema", "reverseema", dict(alpha=0.3)),
    ("autotune_filter", "autotunefilter", dict(window=10, bandwidth=0.3)),
    ("sdo", "sdo", dict(lookback_period=20, period=10, ema_pds=5)),
    ("kinematic_kalman", "kinematickalman", dict(q_pos=0.01, q_vel=0.01, r=1.0)),
]


@pytest.mark.parametrize("slug,batch_fn,params", ONE_IN_CASES, ids=[c[0] for c in ONE_IN_CASES])
def test_one_series_streaming_matches_batch(slug, batch_fn, params):
    cls = qw.streaming_class(slug)
    assert cls is not None, f"streaming_class({slug!r}) is still None"
    st = cls(**params)
    stream_out = [st.next(x) for x in CLOSES]
    batch_out = getattr(_quantwave, batch_fn)(**params, series=CLOSES)
    _assert_series_equal(slug, batch_out, stream_out)


# ---------------------------------------------------------------------------
# (high, low, close) indicators
# ---------------------------------------------------------------------------

HLC_CASES = [
    ("ultosc", "ultosc", dict(timeperiod1=7, timeperiod2=14, timeperiod3=28)),
    ("natr", "natr", dict(timeperiod=14)),
    ("true_range", "truerange", dict()),
    ("typprice", "typprice", dict()),
    ("wclprice", "wclprice", dict()),
    ("adaptive_ema", "adaptiveema", dict(period=14, pds=10)),
    ("tradj_ema", "tradjema", dict(period=14, pds=10, mltp=1.0)),
    ("harrington_adx", "harringtonadx", dict(adx_length=14, adx_smooth_length=6)),
]


@pytest.mark.parametrize("slug,batch_fn,params", HLC_CASES, ids=[c[0] for c in HLC_CASES])
def test_hlc_streaming_matches_batch(slug, batch_fn, params):
    cls = qw.streaming_class(slug)
    assert cls is not None, f"streaming_class({slug!r}) is still None"
    st = cls(**params)
    stream_out = [st.next(h, l, c) for h, l, c in zip(HIGHS, LOWS, CLOSES)]
    batch_out = getattr(_quantwave, batch_fn)(**params, high=HIGHS, low=LOWS, close=CLOSES)
    _assert_series_equal(slug, batch_out, stream_out)


def test_medprice_hl_streaming_matches_batch():
    cls = qw.streaming_class("medprice")
    assert cls is not None
    st = cls()
    stream_out = [st.next(h, l) for h, l in zip(HIGHS, LOWS)]
    batch_out = _quantwave.medprice(high=HIGHS, low=LOWS)
    _assert_series_equal("medprice", batch_out, stream_out)


def test_oc2_co_streaming_matches_batch():
    cls = qw.streaming_class("oc2")
    assert cls is not None
    st = cls()
    stream_out = [st.next(c, o) for c, o in zip(CLOSES, OPENS)]
    batch_out = _quantwave.oc2(close=CLOSES, open=OPENS)
    _assert_series_equal("oc2", batch_out, stream_out)


def test_avgprice_ohlc4_streaming_matches_batch():
    cls = qw.streaming_class("avgprice")
    assert cls is not None
    st = cls()
    stream_out = [st.next(o, h, l, c) for o, h, l, c in zip(OPENS, HIGHS, LOWS, CLOSES)]
    batch_out = _quantwave.avgprice(open=OPENS, high=HIGHS, low=LOWS, close=CLOSES)
    _assert_series_equal("avgprice", batch_out, stream_out)


@pytest.mark.parametrize(
    "slug,batch_fn,params",
    [("mfi", "mfi", dict(timeperiod=14)), ("vpn", "vpn", dict(period=14, smooth_period=3))],
)
def test_hlcv_streaming_matches_batch(slug, batch_fn, params):
    cls = qw.streaming_class(slug)
    assert cls is not None, f"streaming_class({slug!r}) is still None"
    st = cls(**params)
    stream_out = [
        st.next(h, l, c, v) for h, l, c, v in zip(HIGHS, LOWS, CLOSES, VOLUMES)
    ]
    batch_out = getattr(_quantwave, batch_fn)(
        **params, high=HIGHS, low=LOWS, close=CLOSES, volume=VOLUMES
    )
    _assert_series_equal(slug, batch_out, stream_out)


@pytest.mark.parametrize("slug", ["correl", "beta"])
def test_two_series_streaming_matches_batch(slug):
    cls = qw.streaming_class(slug)
    assert cls is not None, f"streaming_class({slug!r}) is still None"
    st = cls(timeperiod=14)
    stream_out = [st.next(a, b) for a, b in zip(CLOSES, HIGHS)]
    batch_out = getattr(_quantwave, slug)(timeperiod=14, real0=CLOSES, real1=HIGHS)
    _assert_series_equal(slug, batch_out, stream_out)


def test_gap_momentum_record_streaming_matches_batch():
    cls = qw.streaming_class("gap_momentum")
    assert cls is not None
    st = cls(period=10, signal_period=3)
    stream_out = [st.next(o, c) for o, c in zip(OPENS, CLOSES)]
    batch_out = _quantwave.gap_momentum(period=10, signal_period=3, open=OPENS, close=CLOSES)
    for i, (s, b) in enumerate(zip(stream_out, batch_out)):
        if s.gap_ratio == s.gap_ratio:  # not NaN
            assert abs(s.gap_ratio - b.gap_ratio) <= 1e-9, i
            assert abs(s.gap_signal - b.gap_signal) <= 1e-9, i


def test_geometric_patterns_streaming_class_constructs_and_runs():
    """geometric_patterns was already fully bound in Rust (GeometricPatternScanner)
    -- streaming_class() just failed to resolve the name. No numeric parity
    fixture exists for its complex (state, flag, hs) output shape, so this
    only checks it constructs and runs without error."""
    cls = qw.streaming_class("geometric_patterns")
    assert cls is not None
    st = cls(5)
    for h, l in zip(HIGHS, LOWS):
        st.next(h, l)


# ---------------------------------------------------------------------------
# Candlestick patterns: all 61 share the same (open, high, low, close) -> f64
# shape and zero-arg constructor.
# ---------------------------------------------------------------------------

CDL_SLUGS = [
    "cdl2crows", "cdl3blackcrows", "cdl3inside", "cdl3linestrike", "cdl3outside",
    "cdl3starsinsouth", "cdl3whitesoldiers", "cdlabandonedbaby", "cdladvanceblock",
    "cdlbelthold", "cdlbreakaway", "cdlclosingmarubozu", "cdlconcealbabyswall",
    "cdlcounterattack", "cdldarkcloudcover", "cdldoji", "cdldojistar",
    "cdldragonflydoji", "cdlengulfing", "cdleveningdojistar", "cdleveningstar",
    "cdlgapsidesidewhite", "cdlgravestonedoji", "cdlhammer", "cdlhangingman",
    "cdlharami", "cdlharamicross", "cdlhighwave", "cdlhikkake", "cdlhikkakemod",
    "cdlhomingpigeon", "cdlidentical3crows", "cdlinneck", "cdlinvertedhammer",
    "cdlkicking", "cdlkickingbylength", "cdlladderbottom", "cdllongleggeddoji",
    "cdllongline", "cdlmarubozu", "cdlmatchinglow", "cdlmathold",
    "cdlmorningdojistar", "cdlmorningstar", "cdlonneck", "cdlpiercing",
    "cdlrickshawman", "cdlrisefall3methods", "cdlseparatinglines",
    "cdlshootingstar", "cdlshortline", "cdlspinningtop", "cdlstalledpattern",
    "cdlsticksandwich", "cdltakuri", "cdltasukigap", "cdlthrusting", "cdltristar",
    "cdlunique3river", "cdlupsidegap2crows", "cdlxsidegap3methods",
]


def test_all_61_candlestick_slugs_covered():
    assert len(CDL_SLUGS) == 61


@pytest.mark.parametrize("slug", CDL_SLUGS)
def test_candlestick_streaming_matches_batch(slug):
    cls = qw.streaming_class(slug)
    assert cls is not None, f"streaming_class({slug!r}) is still None"
    st = cls()
    stream_out = [st.next(o, h, l, c) for o, h, l, c in zip(OPENS, HIGHS, LOWS, CLOSES)]
    batch_out = getattr(_quantwave, slug)(open=OPENS, high=HIGHS, low=LOWS, close=CLOSES)
    _assert_series_equal(slug, batch_out, stream_out)


# ---------------------------------------------------------------------------
# Deliberately-unfixed indicators: still None (see streaming_gap_findings.md).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug", ["hmm_forecast", "lambda_hmm", "sr_monitor"])
def test_deliberately_unfixed_indicators_still_return_none(slug):
    assert qw.streaming_class(slug) is None
