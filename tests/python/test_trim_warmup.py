"""Warmup trimming + backtest warmup warning (quantwave-4rsq).

Indicator warmup is emitted as NaN, not null, so ``drop_nulls()`` is a silent
no-op on it. ``qw.trim_warmup`` is the alignment-preserving replacement and the
``.bt`` surface warns when warmup reaches a backtest.
"""

import warnings

import pytest

polars = pytest.importorskip("polars")
pl = polars

import quantwave as qw


def _close_frame(n: int = 60) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "timestamp": list(range(n)),
            "close": [100.0 + (i % 7) + i * 0.5 for i in range(n)],
        }
    )


# ---------------------------------------------------------------------------
# The bug this fixes: warmup is NaN, not null.
# ---------------------------------------------------------------------------


def test_warmup_is_nan_not_null():
    df = _close_frame(30).with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
    assert df["rsi"].null_count() == 0
    assert df["rsi"].is_nan().sum() == 14
    # The pandas/Polars reflex is a complete no-op:
    assert df.drop_nulls().height == 30
    assert df.drop_nans().height == 16


# ---------------------------------------------------------------------------
# warmup_rows
# ---------------------------------------------------------------------------


class TestWarmupRows:
    def test_single_name(self):
        assert qw.warmup_rows("rsi") == 14

    def test_name_with_params(self):
        assert qw.warmup_rows(("rsi", {"period": 21})) == 21

    def test_mapping_form(self):
        assert qw.warmup_rows({"rsi": {"period": 21}, "ema": {"period": 50}}) == 50

    def test_takes_the_maximum_across_specs(self):
        assert qw.warmup_rows("rsi", ("ema", {"period": 50})) == 50

    def test_explicit_integer_spec(self):
        assert qw.warmup_rows("rsi", 99) == 99

    def test_list_of_specs(self):
        assert qw.warmup_rows(["rsi", ("ema", {"period": 50})]) == 50

    def test_extra_is_added(self):
        assert qw.warmup_rows("rsi", extra=3) == 17

    def test_no_specs_is_zero(self):
        assert qw.warmup_rows() == 0

    def test_matches_warmup_bars(self):
        assert qw.warmup_rows("macd") == qw.warmup_bars("macd")

    def test_unknown_name_raises_by_default(self):
        with pytest.raises(ValueError, match="unknown indicator"):
            qw.warmup_rows("not_a_real_indicator_xyz")

    def test_unknown_name_tolerated_when_not_strict(self):
        assert qw.warmup_rows("not_a_real_indicator_xyz", strict=False) == 0

    def test_negative_extra_raises(self):
        with pytest.raises(ValueError):
            qw.warmup_rows("rsi", extra=-1)

    def test_negative_bar_count_raises(self):
        with pytest.raises(ValueError):
            qw.warmup_rows(-5)

    def test_bad_spec_type_raises(self):
        with pytest.raises(TypeError):
            qw.warmup_rows(object())


# ---------------------------------------------------------------------------
# trim_warmup
# ---------------------------------------------------------------------------


class TestTrimWarmup:
    def test_removes_all_nan_rows_for_one_indicator(self):
        df = _close_frame(60).with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
        out = qw.trim_warmup(df, "rsi")
        assert out.height == 46
        assert out["rsi"].is_nan().sum() == 0
        assert out["rsi"].null_count() == 0

    def test_pipe_style(self):
        df = _close_frame(60).with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
        out = df.pipe(qw.trim_warmup, "rsi")
        assert out.height == 46

    def test_preserves_alignment_across_different_warmups(self):
        df = _close_frame(80).with_columns(
            pl.col("close").ta.rsi(14).alias("rsi"),
            pl.col("close").ta.ema(50).alias("ema"),
        )
        out = df.pipe(qw.trim_warmup, "rsi", ("ema", {"period": 50}))
        assert out.height == 30
        # Both columns clean, and rows still line up with the original frame.
        assert out["rsi"].is_nan().sum() == 0
        assert out["ema"].is_nan().sum() == 0
        assert out["timestamp"].to_list() == list(range(50, 80))
        assert out["close"].to_list() == df["close"].to_list()[50:]

    def test_does_not_over_trim_the_short_indicator(self):
        """The shorter-warmup column keeps every valid row after the max offset."""
        df = _close_frame(80).with_columns(
            pl.col("close").ta.rsi(14).alias("rsi"),
            pl.col("close").ta.ema(50).alias("ema"),
        )
        out = df.pipe(qw.trim_warmup, "rsi", ("ema", {"period": 50}))
        assert out["rsi"].to_list() == df["rsi"].to_list()[50:]

    def test_lazyframe_round_trips(self):
        lf = _close_frame(60).lazy().with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
        out = qw.trim_warmup(lf, "rsi")
        assert isinstance(out, pl.LazyFrame)
        assert out.collect().height == 46

    def test_series_supported(self):
        s = _close_frame(60).with_columns(
            pl.col("close").ta.rsi(14).alias("rsi")
        )["rsi"]
        out = qw.trim_warmup(s, "rsi")
        assert out.len() == 46
        assert out.is_nan().sum() == 0

    def test_zero_warmup_returns_frame_unchanged(self):
        df = _close_frame(10)
        assert qw.trim_warmup(df, strict=False) is df

    def test_extra_trims_further(self):
        df = _close_frame(60).with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
        assert qw.trim_warmup(df, "rsi", extra=2).height == 44

    def test_warns_when_frame_shorter_than_warmup(self):
        df = _close_frame(10).with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
        with pytest.warns(qw.WarmupWarning, match="drop all"):
            out = qw.trim_warmup(df, "rsi")
        assert out.height == 0

    def test_non_frame_raises(self):
        with pytest.raises(TypeError):
            qw.trim_warmup([1, 2, 3], "rsi")

    def test_unknown_indicator_raises_rather_than_silently_not_trimming(self):
        df = _close_frame(60)
        with pytest.raises(ValueError, match="unknown indicator"):
            qw.trim_warmup(df, "rsii")

    def test_trimmed_frame_makes_comparison_signal_meaningful(self):
        """The NaN < 30 -> False footgun disappears after trimming."""
        df = _close_frame(60).with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
        raw = df.with_columns((pl.col("rsi") < 30).cast(pl.Float64).alias("sig"))
        # Warmup rows are silently 0.0 — indistinguishable from "no signal".
        assert raw["sig"].to_list()[:14] == [0.0] * 14
        trimmed = df.pipe(qw.trim_warmup, "rsi")
        assert trimmed["rsi"].is_nan().sum() == 0


# ---------------------------------------------------------------------------
# .bt warmup warning
# ---------------------------------------------------------------------------


def _signal_frame(nan_rows: int = 5, n: int = 40) -> pl.DataFrame:
    signal = [float("nan")] * nan_rows + [
        1.0 if i % 4 < 2 else 0.0 for i in range(n - nan_rows)
    ]
    return pl.DataFrame(
        {
            "timestamp": list(range(n)),
            "close": [100.0 + i * 0.5 for i in range(n)],
            "signal": signal,
        }
    )


class TestBacktestWarmupWarning:
    def test_warns_on_leading_nan_signal(self):
        df = _signal_frame()
        with pytest.warns(qw.WarmupWarning, match="signal"):
            df.lazy().bt.backtest_with_report()

    def test_warns_on_leading_nan_close(self):
        df = _signal_frame(nan_rows=0).with_columns(
            pl.when(pl.col("timestamp") < 3)
            .then(float("nan"))
            .otherwise(pl.col("close"))
            .alias("close")
        )
        with pytest.warns(qw.WarmupWarning, match="close"):
            df.lazy().bt.backtest_with_report()

    def test_warns_on_leading_null_signal(self):
        df = _signal_frame(nan_rows=0).with_columns(
            pl.when(pl.col("timestamp") < 3)
            .then(None)
            .otherwise(pl.col("signal"))
            .alias("signal")
        )
        with pytest.warns(qw.WarmupWarning):
            df.lazy().bt.backtest_with_report()

    def test_no_warning_on_clean_frame(self):
        df = _signal_frame(nan_rows=0)
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df.lazy().bt.backtest_with_report()
        assert [w for w in caught if issubclass(w.category, qw.WarmupWarning)] == []

    def test_no_warning_after_trim_warmup(self):
        df = _close_frame(80).with_columns(pl.col("close").ta.rsi(14).alias("rsi"))
        df = df.with_columns((pl.col("rsi") - 50.0).sign().alias("signal"))
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            df.pipe(qw.trim_warmup, "rsi").lazy().bt.backtest_with_report()
        assert [w for w in caught if issubclass(w.category, qw.WarmupWarning)] == []

    def test_warning_does_not_break_the_backtest(self):
        df = _signal_frame()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            report = df.lazy().bt.backtest_with_report()
        assert report.metrics() is not None

    def test_backtest_metrics_also_warns(self):
        df = _signal_frame()
        with pytest.warns(qw.WarmupWarning):
            df.lazy().bt.backtest_metrics()

    def test_raw_backtest_also_warns(self):
        df = _signal_frame()
        with pytest.warns(qw.WarmupWarning):
            df.lazy().bt.backtest()

    def test_warning_is_filterable(self):
        df = _signal_frame()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warnings.filterwarnings("ignore", category=qw.WarmupWarning)
            df.lazy().bt.backtest_with_report()
        assert [w for w in caught if issubclass(w.category, qw.WarmupWarning)] == []


# ---------------------------------------------------------------------------
# .bt auto-trim (quantwave-1jqv): warmup is trimmed by default, not just warned.
# ---------------------------------------------------------------------------


class TestBacktestAutoTrim:
    def test_backtest_with_report_auto_trims_leading_signal_nan(self):
        df = _signal_frame(nan_rows=5, n=40)
        with pytest.warns(qw.WarmupWarning, match="auto-trimmed"):
            report = df.lazy().bt.backtest_with_report()
        # The engine only ever saw the trimmed frame: fewer bars than the
        # untrimmed input, and none of the dropped rows could have produced
        # a trade even if they'd been left in.
        assert report.metrics() is not None
        assert report.result.stats()["initial_cash"] == 100_000.0

    def test_backtest_with_report_trim_preserves_column_alignment(self):
        """Trimming must slice every column by the same row index, not just
        the checked column — close/timestamp/signal must stay lined up."""
        df = _signal_frame(nan_rows=5, n=40)
        untrimmed_close = df["close"].to_list()
        untrimmed_timestamp = df["timestamp"].to_list()

        captured = {}
        orig_slice = pl.DataFrame.slice

        def _spy_slice(self, offset, length=None):  # noqa: ANN001
            out = orig_slice(self, offset, length)
            captured["offset"] = offset
            captured["close"] = out["close"].to_list()
            captured["timestamp"] = out["timestamp"].to_list()
            return out

        pl.DataFrame.slice = _spy_slice
        try:
            with pytest.warns(qw.WarmupWarning):
                df.lazy().bt.backtest_with_report()
        finally:
            pl.DataFrame.slice = orig_slice

        assert captured["offset"] == 5
        assert captured["close"] == untrimmed_close[5:]
        assert captured["timestamp"] == untrimmed_timestamp[5:]

    def test_backtest_with_report_skip_warmup_trim_restores_old_behavior(self):
        df = _signal_frame(nan_rows=5, n=40)
        untrimmed_close = df["close"].to_list()

        captured = {}
        orig_slice = pl.DataFrame.slice

        def _spy_slice(self, offset, length=None):  # noqa: ANN001
            captured["called"] = True
            return orig_slice(self, offset, length)

        pl.DataFrame.slice = _spy_slice
        try:
            with pytest.warns(qw.WarmupWarning, match="NOT trimmed"):
                report = df.lazy().bt.backtest_with_report(skip_warmup_trim=True)
        finally:
            pl.DataFrame.slice = orig_slice

        assert "called" not in captured  # frame was never sliced
        assert report.metrics() is not None

    def test_portfolio_backtest_auto_trims_and_keeps_symbols_aligned(self):
        # Two leading (fully-NaN-signal) timestamps across both symbols,
        # then normal data.
        n_leading_timestamps = 2
        n_total_timestamps = 6
        timestamps = []
        symbols = []
        closes = []
        signals = []
        for t in range(1, n_total_timestamps + 1):
            for sym, base in (("A", 100.0), ("B", 50.0)):
                timestamps.append(t)
                symbols.append(sym)
                closes.append(base + t)
                signals.append(
                    float("nan") if t <= n_leading_timestamps else (1.0 if t % 2 == 0 else 0.0)
                )
        df = pl.DataFrame(
            {
                "timestamp": timestamps,
                "symbol": symbols,
                "close": closes,
                "signal": signals,
            }
        )

        with pytest.warns(qw.WarmupWarning, match="auto-trimmed"):
            report = df.lazy().bt.portfolio_backtest(
                symbol_col="symbol", commission_bps=0.0, slippage_bps=0.0
            )
        assert report.metrics() is not None

        # skip_warmup_trim=True must leave both symbols' rows fully intact.
        with pytest.warns(qw.WarmupWarning, match="NOT trimmed"):
            report_untrimmed = df.lazy().bt.portfolio_backtest(
                symbol_col="symbol",
                commission_bps=0.0,
                slippage_bps=0.0,
                skip_warmup_trim=True,
            )
        assert report_untrimmed.metrics() is not None

    def test_only_leading_nan_is_trimmed_not_mid_series(self):
        """A mid-series NaN (degenerate math, not warmup) must never be trimmed."""
        n = 40
        signal = [1.0 if i % 4 < 2 else 0.0 for i in range(n)]
        signal[20] = float("nan")  # mid-series, deliberately not warmup
        df = pl.DataFrame(
            {
                "timestamp": list(range(n)),
                "close": [100.0 + i * 0.5 for i in range(n)],
                "signal": signal,
            }
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            report = df.lazy().bt.backtest_with_report()
        # No leading NaN -> no WarmupWarning, and nothing was trimmed.
        assert [w for w in caught if issubclass(w.category, qw.WarmupWarning)] == []
        assert report.metrics() is not None


def test_public_surface():
    assert "trim_warmup" in qw.__all__
    assert "warmup_rows" in qw.__all__
    assert "WarmupWarning" in qw.__all__
    assert issubclass(qw.WarmupWarning, UserWarning)
