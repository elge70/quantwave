"""Polars ``.bt`` namespace for the QuantWave backtest engine.

Importing ``quantwave`` (when Polars and ``quantwave._backtest`` are available)
registers ``LazyFrame.bt`` so you can run simulations without leaving Polars::

    import quantwave
    report = signal_df.lazy().bt.backtest_with_report(
        signal="signal", close_col="close", timestamp_col="bar"
    )

All methods delegate to :class:`quantwave.backtest.BacktestEngine` with a
:class:`quantwave._backtest.BacktestConfig` built from keyword arguments.
The Rust core matches ``quantwave-backtest`` used in native Polars Rust pipelines.
"""

from __future__ import annotations

import warnings

import polars as pl

from quantwave._backtest import BacktestConfig
from quantwave.backtest import BacktestEngine
from quantwave.warmup import WarmupWarning, leading_nan_count


def _detect_warmup(df: pl.DataFrame, *, signal=None, close_col=None) -> tuple[int, list[tuple[str, str, int]]]:
    """Detect leading NaN/null warmup rows in the signal/close columns.

    Returns ``(max_n, findings)`` where ``max_n`` is the number of leading rows
    that are warmup in *any* checked column (the row count to trim so every
    column stays aligned, mirroring how ``trim_warmup()`` takes the max across
    specs) and ``findings`` is a list of ``(role, column_name, n)`` tuples for
    every column that actually has leading warmup.

    Never raises: a detection failure must not break a working backtest.
    """
    try:
        cols = []
        if isinstance(signal, str):
            cols.append(("signal", signal))
        elif isinstance(signal, (list, tuple)):
            cols.extend(("signal", c) for c in signal if isinstance(c, str))
        if isinstance(close_col, str):
            cols.append(("close", close_col))

        available = set(df.columns)
        findings: list[tuple[str, str, int]] = []
        max_n = 0
        for role, name in cols:
            if name not in available:
                continue
            n = leading_nan_count(df.get_column(name))
            if n <= 0:
                continue
            findings.append((role, name, n))
            max_n = max(max_n, n)
        return max_n, findings
    except Exception:  # pragma: no cover - detection must never break a backtest
        return 0, []


def _handle_warmup(
    df: pl.DataFrame,
    *,
    signal=None,
    close_col=None,
    method="backtest",
    skip_warmup_trim: bool = False,
) -> pl.DataFrame:
    """Detect leading warmup rows and, by default, trim them before backtesting.

    QuantWave indicators emit warmup as NaN, not null, so ``drop_nulls()`` does
    not remove it and warmup silently reaches the engine. By default this now
    auto-trims the detected leading rows (same detection ``trim_warmup()``
    uses, via :func:`quantwave.warmup.leading_nan_count`) so a backtest never
    silently runs through warmup. A ``WarmupWarning`` still fires either way,
    so callers learn their data had warmup — the wording differs depending on
    whether the rows were trimmed or (with ``skip_warmup_trim=True``) left in
    place.

    Only ever slices LEADING rows off the front of the frame, by row index
    across every column — never touches mid-series NaN (degenerate math like
    div-by-zero is a distinct, real signal and is left alone).

    Never raises: a detection failure must not break a working backtest.
    """
    try:
        max_n, findings = _detect_warmup(df, signal=signal, close_col=close_col)
        if not findings:
            return df

        detail = ", ".join(f"{role} column {name!r} ({n} row(s))" for role, name, n in findings)

        if skip_warmup_trim:
            warnings.warn(
                f"{method}: {detail} start with NaN/null warmup rows — these look "
                "like indicator warmup. QuantWave emits warmup as NaN, not null, so "
                "drop_nulls() does NOT remove it and NaN comparisons silently "
                "evaluate to False (a 0.0 signal is indistinguishable from a real "
                "no-signal bar). skip_warmup_trim=True was passed, so these rows "
                "were NOT trimmed automatically — trim manually, e.g. "
                'df.pipe(quantwave.trim_warmup, "rsi", ("ema", {"period": 50})), '
                "or use drop_nans(). Silence with "
                "warnings.filterwarnings('ignore', category=quantwave.WarmupWarning).",
                WarmupWarning,
                stacklevel=4,
            )
            return df

        warnings.warn(
            f"{method}: {detail} started with NaN/null warmup rows — auto-trimmed "
            f"the leading {max_n} row(s) from the frame before backtesting "
            "(QuantWave emits warmup as NaN, not null, so drop_nulls() would not "
            "have caught this; only leading rows were trimmed, never mid-series "
            "NaN). Pass skip_warmup_trim=True to restore the old warn-only "
            "behavior. Silence entirely with "
            "warnings.filterwarnings('ignore', category=quantwave.WarmupWarning).",
            WarmupWarning,
            stacklevel=4,
        )
        return df.slice(max_n)
    except Exception:  # pragma: no cover - detection must never break a backtest
        return df


def _config_from_kwargs(
    *,
    signal: str = "signal",
    timestamp_col: str = "timestamp",
    close_col: str = "close",
    high_col: str | None = None,
    low_col: str | None = None,
    symbol_col: str | None = None,
    entry_filter_col: str | None = None,
    size_multiplier_col: str | None = None,
    initial_cash: float = 100_000.0,
    commission_bps: float = 5.0,
    slippage_bps: float = 2.0,
    execution_delay: str = "next_bar",
    stop_loss_pct: float | None = None,
    take_profit_pct: float | None = None,
    trailing_stop_pct: float | None = None,
    touched_exit: bool = False,
    portfolio_mode: str = "independent_books",
    portfolio_allocator: str = "equal_weight",
    signal_type: str = "weight",
    risk_model: dict | None = None,
    rebalance_policy: dict | None = None,
) -> BacktestConfig:
    return BacktestConfig(
        signal_col=signal,
        timestamp_col=timestamp_col,
        close_col=close_col,
        high_col=high_col,
        low_col=low_col,
        symbol_col=symbol_col,
        entry_filter_col=entry_filter_col,
        size_multiplier_col=size_multiplier_col,
        initial_cash=initial_cash,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        execution_delay=execution_delay,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
        trailing_stop_pct=trailing_stop_pct,
        touched_exit=touched_exit,
        portfolio_mode=portfolio_mode,
        portfolio_allocator=portfolio_allocator,
        signal_type=signal_type,
        risk_model=risk_model,
        rebalance_policy=rebalance_policy,
    )


@pl.api.register_lazyframe_namespace("bt")
class BtLazyNamespace:
    """Backtest methods on ``LazyFrame`` via ``df.lazy().bt.*``.

    Typical columns: ``timestamp``, ``close``, ``signal`` (long/short/flat encoding).
    See https://lavs9.github.io/quantwave/guides/backtest/quickstart/ for signal
    conventions and portfolio modes.
    See https://lavs9.github.io/quantwave/guides/backtest/output-contract/ for output schema.

    Primary entry points:

    * :meth:`backtest_with_report` — metrics + trades + equity (recommended)
    * :meth:`backtest` — raw :class:`~quantwave._backtest.BacktestResult`
    * :meth:`portfolio_backtest` — shared-capital multi-symbol book
    * :meth:`sweep` / :meth:`walk_forward_optimize` — research workflows
    """

    def __init__(self, ldf: pl.LazyFrame) -> None:
        """Attach the namespace to a lazy frame (called by Polars)."""
        self._ldf = ldf

    def backtest(
        self,
        signal: str = "signal",
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        high_col: str | None = None,
        low_col: str | None = None,
        symbol_col: str | None = None,
        entry_filter_col: str | None = None,
        size_multiplier_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        touched_exit: bool = False,
        risk_model: dict | None = None,
        skip_warmup_trim: bool = False,
    ):
        """Run a backtest and return the raw :class:`BacktestResult`.

        Args:
            risk_model: Optional dict of risk overlays applied to the target
                exposure at entry, e.g.
                ``{"vol_target": {"target_annual_vol": 0.15, "lookback": 20},
                "position_limit": {"max_abs_exposure": 50.0}}``. Only the
                overlay keys present are applied; omitted overlays (and the
                default ``None``) leave sizing untouched (byte-identical to
                today's behavior). Overlays size a position **at entry**
                only — the engine does not resize an already-open position
                intra-trade. Supported keys: ``vol_target``, ``inverse_vol``,
                ``position_limit``, ``pre_trade``. See
                ``quantwave-backtest/src/risk.rs`` for each sub-config's
                fields.
            skip_warmup_trim: By default, leading NaN/null warmup rows in the
                ``signal``/``close_col`` columns are detected and trimmed
                before running the backtest (a ``WarmupWarning`` still fires
                so you learn your data had warmup). Pass ``True`` to restore
                the old warn-only behavior and run through untrimmed warmup.
        """
        config = _config_from_kwargs(
            signal=signal,
            timestamp_col=timestamp_col,
            close_col=close_col,
            high_col=high_col,
            low_col=low_col,
            symbol_col=symbol_col,
            entry_filter_col=entry_filter_col,
            size_multiplier_col=size_multiplier_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            touched_exit=touched_exit,
            risk_model=risk_model,
        )
        df = self._ldf.collect()
        df = _handle_warmup(
            df, signal=signal, close_col=close_col, method="backtest",
            skip_warmup_trim=skip_warmup_trim,
        )
        return BacktestEngine(config).run(df)

    def backtest_with_report(
        self,
        signal: str = "signal",
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        high_col: str | None = None,
        low_col: str | None = None,
        symbol_col: str | None = None,
        entry_filter_col: str | None = None,
        size_multiplier_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        touched_exit: bool = False,
        risk_model: dict | None = None,
        skip_warmup_trim: bool = False,
    ):
        """Run a backtest and return a full report (metrics, trades, equity).

        This is the recommended high-level API for strategy evaluation.

        Args:
            signal: Column name with position signal (-1, 0, 1 or strategy-specific).
            timestamp_col: Monotonic bar index or datetime column.
            close_col: Price column for mark-to-market and fills.
            symbol_col: Optional symbol column for per-symbol books.
            entry_filter_col: Optional boolean column to gate entries.
            size_multiplier_col: Optional sizing multiplier per bar.
            initial_cash: Starting capital.
            commission_bps: Commission in basis points per trade leg.
            slippage_bps: Slippage in basis points.
            execution_delay: Fill timing. ``"next_bar"`` (default) fills a signal
                from bar *t* at bar *t+1*'s close — no same-bar look-ahead.
                ``"same_bar"`` fills at bar *t*'s own close; only honest for
                close-auction execution or signals built purely from bar *t-1*
                data, and systematically optimistic otherwise.
            stop_loss_pct: Optional stop-loss fraction (e.g. ``0.02`` for 2%).
            take_profit_pct: Optional take-profit fraction.
            trailing_stop_pct: Optional trailing stop fraction.
            high_col: Bar high column (required when ``touched_exit=True``).
            low_col: Bar low column (required when ``touched_exit=True``).
            touched_exit: Use OHLC intrabar stop/target detection (polars-backtest style).
            risk_model: Optional dict of risk overlays applied to the target
                exposure at entry, e.g.
                ``{"vol_target": {"target_annual_vol": 0.15, "lookback": 20},
                "position_limit": {"max_abs_exposure": 50.0}}``. Only the
                overlay keys present are applied; the default ``None``
                leaves sizing byte-identical to today's behavior. Overlays
                size a position **at entry** only — no intra-trade
                resizing. Supported keys: ``vol_target``, ``inverse_vol``,
                ``position_limit``, ``pre_trade``.
            skip_warmup_trim: By default, leading NaN/null warmup rows in the
                ``signal``/``close_col`` columns are detected and trimmed
                before running the backtest (a ``WarmupWarning`` still fires
                so you learn your data had warmup). Pass ``True`` to restore
                the old warn-only behavior and run through untrimmed warmup.

        Returns:
            BacktestReport with ``metrics``, ``trades``, and equity series accessors.

        Example:
            >>> import polars as pl
            >>> import quantwave  # registers .bt
            >>> df = pl.DataFrame({
            ...     "timestamp": [0, 1, 2],
            ...     "close": [100.0, 101.0, 102.0],
            ...     "signal": [0, 1, 0],
            ... })
            >>> report = df.lazy().bt.backtest_with_report(
            ...     signal="signal", close_col="close", timestamp_col="timestamp"
            ... )
            >>> report_capped = df.lazy().bt.backtest_with_report(
            ...     signal="signal", close_col="close", timestamp_col="timestamp",
            ...     risk_model={"position_limit": {"max_abs_exposure": 5.0}},
            ... )
        """
        config = _config_from_kwargs(
            signal=signal,
            timestamp_col=timestamp_col,
            close_col=close_col,
            high_col=high_col,
            low_col=low_col,
            symbol_col=symbol_col,
            entry_filter_col=entry_filter_col,
            size_multiplier_col=size_multiplier_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            touched_exit=touched_exit,
            risk_model=risk_model,
        )
        df = self._ldf.collect()
        df = _handle_warmup(
            df, signal=signal, close_col=close_col, method="backtest_with_report",
            skip_warmup_trim=skip_warmup_trim,
        )
        return BacktestEngine(config).backtest_with_report(df)

    def backtest_metrics(
        self,
        signal: str = "signal",
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        symbol_col: str | None = None,
        entry_filter_col: str | None = None,
        size_multiplier_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        risk_model: dict | None = None,
        skip_warmup_trim: bool = False,
    ) -> dict[str, float]:
        """Run a backtest and return only the metrics dict.

        Args:
            risk_model: Optional risk-overlay dict; see
                :meth:`backtest_with_report` for the full schema. Default
                ``None`` leaves sizing byte-identical to today's behavior.
            skip_warmup_trim: By default, leading NaN/null warmup rows in the
                ``signal``/``close_col`` columns are detected and trimmed
                before running the backtest (a ``WarmupWarning`` still fires
                so you learn your data had warmup). Pass ``True`` to restore
                the old warn-only behavior and run through untrimmed warmup.
        """
        config = _config_from_kwargs(
            signal=signal,
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            entry_filter_col=entry_filter_col,
            size_multiplier_col=size_multiplier_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            risk_model=risk_model,
        )
        df = self._ldf.collect()
        df = _handle_warmup(
            df, signal=signal, close_col=close_col, method="backtest_metrics",
            skip_warmup_trim=skip_warmup_trim,
        )
        return BacktestEngine(config).run_metrics_only(df)

    def portfolio_backtest(
        self,
        *,
        signal: str = "signal",
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        symbol_col: str = "symbol",
        entry_filter_col: str | None = None,
        size_multiplier_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        portfolio_mode: str = "shared_capital",
        portfolio_allocator: str = "equal_weight",
        signal_type: str = "weight",
        rebalance_policy: dict | None = None,
        skip_warmup_trim: bool = False,
    ):
        """Shared-capital multi-symbol backtest.

        Args:
            signal_type: How signal magnitude is interpreted when sizing a
                new entry. ``"weight"`` (default) — a
                fraction of total equity independent per symbol, e.g. 0.1 =
                10% of equity in that symbol (not normalized against peers;
                caller keeps the sum of active weights sane). Matches
                zipline ``order_target_percent`` / backtrader
                ``PercentSizer`` / QuantConnect ``SetHoldings`` / vectorbt
                ``targetpercent`` convention. ``"target_pct"`` — a weight
                normalized across all symbols with a non-zero signal this
                bar (today's ``portfolio_allocator="signal_weighted"``
                budget math, without a clamp). ``"shares"`` — signal
                magnitude as a literal share count, the historical
                behavior: this silently clamps equity-based position sizing
                down to ~1 share for a boolean (0/1) signal, so a large book
                will not deploy its capital. The default changed from
                ``"shares"`` to ``"weight"`` (breaking
                change, explicitly decided 2026-09-08) — pass
                ``signal_type="shares"`` to keep the old behavior.
            rebalance_policy: Optional dict gating when signal-driven
                entries/exits/flips are re-evaluated, e.g.
                ``{"calendar": {"every_n_bars": 5}}``,
                ``{"drift": {"threshold": 0.05}}``, ``{"signal": {}}``, or
                ``{"turnover": {"min_turnover": 0.02}}``. Exactly one
                top-level key. Default ``None`` rebalances every bar
                (byte-identical to today's behavior). Stop-loss /
                take-profit / trailing-stop exits are always evaluated
                regardless of this policy.
            skip_warmup_trim: By default, leading NaN/null warmup rows in the
                ``signal``/``close_col`` columns are detected and trimmed
                before running the backtest (a ``WarmupWarning`` still fires
                so you learn your data had warmup). Pass ``True`` to restore
                the old warn-only behavior and run through untrimmed warmup.
        """
        config = _config_from_kwargs(
            signal=signal,
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            entry_filter_col=entry_filter_col,
            size_multiplier_col=size_multiplier_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            portfolio_mode=portfolio_mode,
            portfolio_allocator=portfolio_allocator,
            signal_type=signal_type,
            rebalance_policy=rebalance_policy,
        )
        df = self._ldf.collect()
        df = _handle_warmup(
            df, signal=signal, close_col=close_col, method="portfolio_backtest",
            skip_warmup_trim=skip_warmup_trim,
        )
        return BacktestEngine(config).backtest_with_report(df)

    def sweep(
        self,
        *,
        param_name: str,
        param_values: list[float],
        signal_cols: list[str],
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        symbol_col: str | None = None,
        entry_filter_col: str | None = None,
        size_multiplier_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        skip_warmup_trim: bool = False,
    ) -> pl.DataFrame:
        """Run one backtest per param value; return param × metrics DataFrame."""
        if len(param_values) != len(signal_cols):
            raise ValueError(
                f"param_values len {len(param_values)} != signal_cols len {len(signal_cols)}"
            )
        if not param_values:
            raise ValueError("sweep requires at least one variant")

        base_kwargs = dict(
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            entry_filter_col=entry_filter_col,
            size_multiplier_col=size_multiplier_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
            skip_warmup_trim=skip_warmup_trim,
        )

        rows: list[dict[str, float]] = []
        for value, signal_col in zip(param_values, signal_cols, strict=True):
            report = self.backtest_with_report(signal=signal_col, **base_kwargs)
            row = {param_name: value, **report.metrics()}
            rows.append(row)

        return pl.DataFrame(rows)

    def sweep_callback(
        self,
        *,
        param_grid: dict[str, list[float]],
        build_fn,
        signal: str = "signal",
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        symbol_col: str | None = None,
        entry_filter_col: str | None = None,
        size_multiplier_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        trailing_stop_pct: float | None = None,
    ) -> pl.DataFrame:
        import itertools
        if not param_grid:
            raise ValueError("param_grid cannot be empty")
        if not callable(build_fn):
            raise ValueError("build_fn must be callable")
            
        base_kwargs = dict(
            signal=signal,
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            entry_filter_col=entry_filter_col,
            size_multiplier_col=size_multiplier_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
        )
        keys = list(param_grid.keys())
        values_lists = [param_grid[k] for k in keys]
        rows = []
        for combo in itertools.product(*values_lists):
            params = dict(zip(keys, combo))
            built_lf = build_fn(self._ldf, params)
            if signal not in built_lf.collect_schema().names():
                raise ValueError(f"build_fn must return a frame with signal column '{signal}'")
            config = _config_from_kwargs(**base_kwargs)
            report = BacktestEngine(config).backtest_with_report(built_lf.collect())
            row = {**params, **report.metrics()}
            rows.append(row)
        return pl.DataFrame(rows)

    def walk_forward(
        self,
        *,
        train_bars: int,
        test_bars: int,
        step_bars: int | None = None,
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        signal: str = "signal",
        symbol_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        skip_warmup_trim: bool = False,
    ) -> pl.DataFrame:
        """Rolling OOS walk-forward → fold × metrics DataFrame (delegates to Rust).

        Args:
            skip_warmup_trim: By default, leading NaN/null warmup rows in the
                ``signal``/``close_col`` columns are detected and trimmed
                before running (a ``WarmupWarning`` still fires so you learn
                your data had warmup). Pass ``True`` to restore the old
                warn-only behavior and run through untrimmed warmup.
        """
        if train_bars <= 0 or test_bars <= 0:
            raise ValueError("train_bars and test_bars must be > 0")

        from quantwave._backtest import run_walk_forward_py

        config = _config_from_kwargs(
            signal=signal,
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
        )
        df = self._ldf.collect()
        df = _handle_warmup(
            df, signal=signal, close_col=close_col, method="walk_forward",
            skip_warmup_trim=skip_warmup_trim,
        )
        return run_walk_forward_py(
            df,
            config,
            train_bars,
            test_bars,
            step_bars,
        )

    def walk_forward_optimize(
        self,
        *,
        param_grid: dict[str, list[float]],
        build_fn,
        objective: str = "sharpe_ratio",
        train_bars: int,
        test_bars: int,
        step_bars: int | None = None,
        overfit_threshold: float = 1.0,
        optimizer: str = "grid",
        n_trials: int | None = None,
        seed: int = 42,
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        signal: str = "signal",
        symbol_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
    ) -> pl.DataFrame:
        """Walk-forward with train-window parameter optimization (Rust core).

        ``optimizer`` selects the in-fold parameter search strategy:

        * ``"grid"`` (default) — exhaustively backtests every ``param_grid``
          combination on each training fold, exactly as before.
        * ``"tpe"`` — Bayesian alternative (Tree-structured Parzen Estimator,
          Bergstra et al. 2011). Instead of backtesting the full grid, it
          adaptively backtests only ``n_trials`` combinations per fold, useful
          when ``param_grid`` is large. Requires ``n_trials``. Deterministic
          given ``seed``.
        """
        import itertools

        if not param_grid:
            raise ValueError("param_grid cannot be empty")
        if not callable(build_fn):
            raise ValueError("build_fn must be callable")
        if train_bars <= 0 or test_bars <= 0:
            raise ValueError("train_bars and test_bars must be > 0")
        if optimizer not in ("grid", "tpe"):
            raise ValueError("optimizer must be 'grid' or 'tpe'")
        if optimizer == "tpe" and not n_trials:
            raise ValueError("n_trials is required when optimizer='tpe'")

        from quantwave._backtest import run_walk_forward_optimize_py

        df = self._ldf.collect()
        keys = list(param_grid.keys())
        values_lists = [param_grid[k] for k in keys]

        enriched = df.clone()
        variants: list[tuple[dict[str, float], str]] = []
        for combo in itertools.product(*values_lists):
            params = dict(zip(keys, combo, strict=True))
            sig_col = "__qw_wfo_" + "_".join(f"{k}{v:g}" for k, v in params.items())
            built = build_fn(self._ldf, params).collect()
            if signal not in built.columns:
                raise ValueError(f"build_fn must return a frame with signal column '{signal}'")
            if built.height != enriched.height:
                raise ValueError("build_fn must preserve row count of input frame")
            enriched = enriched.with_columns(built[signal].alias(sig_col))
            variants.append((params, sig_col))

        config = _config_from_kwargs(
            signal=variants[0][1],
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
        )
        return run_walk_forward_optimize_py(
            enriched,
            config,
            train_bars,
            test_bars,
            variants,
            objective,
            step_bars,
            overfit_threshold,
        )

    def cross_sectional_backtest(
        self,
        *,
        factor_col: str,
        top_frac: float = 0.2,
        bottom_frac: float = 0.2,
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        symbol_col: str = "symbol",
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        transform: str | None = None,
    ):
        """sigc-inspired rank → long/short panel backtest (cr6v.15)."""
        if top_frac <= 0 or bottom_frac <= 0 or top_frac + bottom_frac > 1.0:
            raise ValueError("invalid top_frac/bottom_frac")

        df = self._ldf.collect()
        
        if transform == "zscore":
            mean = pl.col(factor_col).mean().over(timestamp_col)
            std = pl.col(factor_col).std(ddof=1).over(timestamp_col)
            df = df.with_columns(((pl.col(factor_col) - mean) / std).alias(factor_col))
        elif transform == "neutralize":
            mean = pl.col(factor_col).mean().over(timestamp_col)
            df = df.with_columns((pl.col(factor_col) - mean).alias(factor_col))
        elif transform == "winsorize":
            lower = pl.col(factor_col).quantile(0.05).over(timestamp_col)
            upper = pl.col(factor_col).quantile(0.95).over(timestamp_col)
            df = df.with_columns(
                pl.col(factor_col).clip(lower_bound=lower, upper_bound=upper).alias(factor_col)
            )
            
        ranked = (
            df.with_columns(
                pl.col(factor_col)
                .rank(method="min", descending=True)
                .over(timestamp_col)
                .alias("_rank"),
                pl.col(timestamp_col).count().over(timestamp_col).alias("_n"),
            )
            .with_columns(
                pl.when(
                    pl.col("_rank")
                    <= (pl.col("_n") * top_frac).ceil().clip(lower_bound=1)
                )
                .then(1.0 / (pl.col("_n") * top_frac).ceil().clip(lower_bound=1))
                .when(
                    pl.col("_rank")
                    >= pl.col("_n")
                    - (pl.col("_n") * bottom_frac).ceil().clip(lower_bound=1)
                    + 1
                )
                .then(
                    -1.0 / (pl.col("_n") * bottom_frac).ceil().clip(lower_bound=1)
                )
                .otherwise(0.0)
                .alias("cs_exposure")
            )
        )
        config = _config_from_kwargs(
            signal="cs_exposure",
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
        )
        return BacktestEngine(config).backtest_with_report(ranked)

    def order_backtest(
        self,
        orders: pl.DataFrame | pl.LazyFrame,
        *,
        timestamp_col: str = "timestamp",
        open_col: str = "open",
        high_col: str = "high",
        low_col: str = "low",
        close_col: str = "close",
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        skip_warmup_trim: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Order-driven backtest: explicit per-bar orders instead of a signal column.

        Unlike :meth:`backtest` (which derives entries/exits from a ``signal``
        column), this drives the flat/single-position order-execution core
        directly (``quantwave-backtest::order_exec``) with first-class
        ``Order`` objects — market / limit / stop / stop-limit — resolved
        deterministically against each bar's OHLC.

        Position model: flat-or-single-position, no pyramiding. An order that
        fills while flat opens a position; an opposite-side fill closes it
        (records a trade); a same-side fill while already in a position is
        ignored. Any open position is flattened at the final bar's close.

        Args:
            orders: Long-format order spec, one row per order, with columns:

                * ``bar_index`` (int) — 0-based row index into ``df`` this
                  order is submitted/resting for.
                * ``side`` (str) — ``"buy"`` or ``"sell"``.
                * ``type`` (str) — ``"market"``, ``"limit"``, ``"stop"``, or
                  ``"stop_limit"``.
                * ``qty`` (float) — order quantity (units).
                * ``price`` (float, nullable) — limit level for ``"limit"``/
                  ``"stop_limit"`` (the stop-limit's limit leg); unused for
                  ``"market"``/``"stop"``.
                * ``trigger`` (float, nullable) — breakout/stop level for
                  ``"stop"``/``"stop_limit"``; unused for ``"market"``/
                  ``"limit"``.
                * ``take_profit`` / ``stop_loss`` (float, nullable, optional
                  columns) — when *both* are set on an entry row, attach a
                  protective **bracket** (OCO exit pair) to the resulting
                  position. Once open, the bracket is checked against every
                  subsequent bar's OHLC; a same-bar double-touch resolves
                  stop-before-target (pessimistic). Supplying only one leg
                  raises. Omit the columns entirely for plain orders.
            timestamp_col: Monotonic bar index or datetime column on ``df``.
            open_col, high_col, low_col, close_col: OHLC columns on ``df``.
            initial_cash: Starting capital.
            commission_bps: Commission in basis points per trade leg.
            slippage_bps: Slippage in basis points applied to fill price.
            skip_warmup_trim: By default, leading NaN/null warmup rows in
                ``close_col`` are detected and trimmed before running (a
                ``WarmupWarning`` still fires so you learn your data had
                warmup). Because ``orders.bar_index`` indexes into ``df``,
                trimming here also drops any order whose ``bar_index`` falls
                inside the trimmed region and shifts the rest so they still
                point at the correct (now-renumbered) bar — a second
                ``WarmupWarning`` fires if any orders were dropped this way.
                Pass ``True`` to restore the old warn-only behavior and run
                through untrimmed warmup with ``orders`` unchanged.

        Returns:
            ``(trades_df, equity_df)`` — same column shape as
            :meth:`backtest`'s ``BacktestResult.trades`` /
            ``.equity_curve`` (single-symbol, no ``symbol`` column).

        Example:
            >>> import polars as pl
            >>> import quantwave  # registers .bt
            >>> bars = pl.DataFrame({
            ...     "timestamp": [0, 1, 2, 3],
            ...     "open": [100.0, 101.0, 103.0, 104.0],
            ...     "high": [101.0, 103.0, 105.0, 106.0],
            ...     "low": [99.0, 100.0, 101.0, 98.0],
            ...     "close": [100.5, 102.0, 104.0, 99.0],
            ... })
            >>> orders = pl.DataFrame({
            ...     "bar_index": [0, 3],
            ...     "side": ["buy", "sell"],
            ...     "type": ["market", "market"],
            ...     "qty": [10.0, 10.0],
            ...     "price": [None, None],
            ...     "trigger": [None, None],
            ... })
            >>> trades, equity = bars.lazy().bt.order_backtest(orders)
        """
        from quantwave._backtest import order_backtest_py

        orders_df = orders.collect() if isinstance(orders, pl.LazyFrame) else orders
        df = self._ldf.collect()

        n, findings = _detect_warmup(df, close_col=close_col)
        if findings:
            detail = ", ".join(f"{role} column {name!r} ({cnt} row(s))" for role, name, cnt in findings)
            if skip_warmup_trim:
                warnings.warn(
                    f"order_backtest: {detail} start with NaN/null warmup rows — "
                    "skip_warmup_trim=True was passed, so these rows were NOT "
                    "trimmed automatically. Silence with "
                    "warnings.filterwarnings('ignore', category=quantwave.WarmupWarning).",
                    WarmupWarning,
                    stacklevel=2,
                )
            else:
                warnings.warn(
                    f"order_backtest: {detail} started with NaN/null warmup rows — "
                    f"auto-trimmed the leading {n} row(s) from the frame before "
                    "backtesting. Pass skip_warmup_trim=True to restore the old "
                    "warn-only behavior. Silence entirely with "
                    "warnings.filterwarnings('ignore', category=quantwave.WarmupWarning).",
                    WarmupWarning,
                    stacklevel=2,
                )
                df = df.slice(n)
                bar_idx = orders_df.get_column("bar_index")
                dropped = int((bar_idx < n).sum())
                if dropped:
                    warnings.warn(
                        f"order_backtest: dropped {dropped} order(s) whose bar_index "
                        f"fell inside the {n} auto-trimmed warmup row(s); the "
                        "remaining orders' bar_index was shifted to match the "
                        "trimmed frame.",
                        WarmupWarning,
                        stacklevel=2,
                    )
                orders_df = orders_df.filter(bar_idx >= n).with_columns(
                    (pl.col("bar_index") - n).alias("bar_index")
                )

        return order_backtest_py(
            df,
            orders_df,
            timestamp_col=timestamp_col,
            open_col=open_col,
            high_col=high_col,
            low_col=low_col,
            close_col=close_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
        )

    def monte_carlo(
        self,
        *,
        signal: str = "signal",
        timestamp_col: str = "timestamp",
        close_col: str = "close",
        symbol_col: str | None = None,
        entry_filter_col: str | None = None,
        size_multiplier_col: str | None = None,
        initial_cash: float = 100_000.0,
        commission_bps: float = 5.0,
        slippage_bps: float = 2.0,
        execution_delay: str = "next_bar",
        stop_loss_pct: float | None = None,
        take_profit_pct: float | None = None,
        trailing_stop_pct: float | None = None,
        n_simulations: int = 1000,
        seed: int = 42,
        mode: str = "trade_bootstrap",
        n_bars_forward: int = 252,
        skip_warmup_trim: bool = False,
    ) -> dict:
        """Run backtest then Monte Carlo robustness.

        Args:
            mode: ``trade_bootstrap`` (resample closed-trade PnLs) or
                ``return_paths`` (return-path VaR/CVaR).
            skip_warmup_trim: By default, leading NaN/null warmup rows in the
                ``signal``/``close_col`` columns are detected and trimmed
                before running (a ``WarmupWarning`` still fires so you learn
                your data had warmup). Pass ``True`` to restore the old
                warn-only behavior and run through untrimmed warmup.
        """
        config = _config_from_kwargs(
            signal=signal,
            timestamp_col=timestamp_col,
            close_col=close_col,
            symbol_col=symbol_col,
            entry_filter_col=entry_filter_col,
            size_multiplier_col=size_multiplier_col,
            initial_cash=initial_cash,
            commission_bps=commission_bps,
            slippage_bps=slippage_bps,
            execution_delay=execution_delay,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            trailing_stop_pct=trailing_stop_pct,
        )
        from quantwave._backtest import (
            monte_carlo_return_paths_py,
            monte_carlo_trade_bootstrap_py,
        )

        df = self._ldf.collect()
        df = _handle_warmup(
            df, signal=signal, close_col=close_col, method="monte_carlo",
            skip_warmup_trim=skip_warmup_trim,
        )
        result = BacktestEngine(config).run(df)
        if mode == "return_paths":
            return monte_carlo_return_paths_py(
                result._inner,
                n_simulations=n_simulations,
                seed=seed,
                n_bars_forward=n_bars_forward,
            )
        if mode != "trade_bootstrap":
            raise ValueError("mode must be 'trade_bootstrap' or 'return_paths'")
        return monte_carlo_trade_bootstrap_py(
            result._inner,
            initial_cash=initial_cash,
            n_simulations=n_simulations,
            seed=seed,
        )