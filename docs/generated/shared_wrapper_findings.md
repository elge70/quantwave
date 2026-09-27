# Shared streaming-result wrapper structs (PyO3 bindings)

Investigation triggered by the discovery that `ttm_squeeze.next()` returned an
object whose Python `type()` was `SuperTrendResult` (quantwave-lt3t, item #3).
Root cause: the `export_*_in_record_out!` macro family in
`quantwave-py/src/indicators.rs` takes the result struct as a parameter, and
several indicators pass in a struct originally defined for a different (but
structurally identical, `(f64, f64)`-shaped) indicator instead of defining
their own.

## Method

Every invocation of the `_record_out!` macro variants
(`export_1_in_record_out!`, `export_ohlc_in_record_out!`,
`export_hl_in_record_out!`, `export_co_in_record_out!`,
`export_pv_in_record_out!`) in `quantwave-py/src/indicators.rs` was enumerated
(27 invocations total) and grouped by the result-struct name each one passes.
Manual (non-macro) `#[pyclass]`/`#[pymethods]` blocks were also checked and
each returns a uniquely-named struct (`DonchianResult`, `HeikinAshiResult`,
`PivotPointsResult`, `VolumeProfileResult`, `CycleTrendAnalyticsResult`, etc.)
— the sharing pattern only occurs among macro invocations.

## Struct names reused by more than one indicator

| Wrapper struct | Fields | Indicators using it | Shape match | Semantic match |
|---|---|---|---|---|
| `SuperTrendResult` | `value: f64, direction: i8` | `SuperTrend` (native owner), `TtmSqueeze` (**fixed in this change**, see below) | Yes | **No** — see below |
| `CyberCycleResult` | `value: f64, trigger: f64` | `CyberCycle` (native owner), `ChannelCycle` | Yes | Yes — both are cycle-oscillator value + trigger/signal line, same DSP concept (Channel Cycle is a documented variant of the Cyber Cycle) |
| `PhasorResult` | `in_phase: f64, quadrature: f64` | `Phasor` (native owner), `CorrelationCycle`, `SineWave`, `HtPhasor` | Yes | Yes — all four are Hilbert-transform/quadrature-style outputs; "in-phase/quadrature" is a generic DSP term, not something specific to the `Phasor` indicator alone |
| `TrendRocResult` | `trend: f64, roc: f64` | `PrecisionTrend`, `ReversionIndex` (no indicator literally named "TrendRoc" — the struct name is intentionally generic) | Yes | Yes — both indicators emit a smoothed trend value plus its rate-of-change, same meaning in both |

All other macro-generated result structs (`MacdResult`, `AroonResult`,
`MamaResult`, `AlligatorResult`, `AtrTsResult`, `EmdResult`,
`EhlersLoopsResult`, `FractalsResult`, `ZeroLagResult`, `UdmaResult`,
`PairsRotationResult`, `PmaResult`, `SystemEvaluatorResult`, `VortexResult`,
`WaveTrendResult`, `VossPredictorResult`, `HtSineResult`) are each used by
exactly one indicator — no sharing.

## The one real mismatch: `SuperTrendResult` vs `TtmSqueeze`

This is qualitatively different from the other three groups:

- `SuperTrend`'s `direction: i8` is a genuine trend-direction flag in
  `{-1, +1}` (`quantwave-core/src/indicators/supertrend.rs:44`,
  `// 1 for up, -1 for down`), and `value` is the SuperTrend price level.
- `TtmSqueeze`'s second output is `is_squeezed: bool`
  (`quantwave-core/src/indicators/ttm_squeeze.rs:55`), cast to `0`/`1` at the
  PyO3 boundary — a squeeze-on/off state flag, not a direction — and `value`
  is a momentum histogram, not a price level.

So `type(result).__name__ == "SuperTrendResult"` for a TTM Squeeze result was
actively misleading (wrong indicator name *and* a field whose name overlaps
but whose meaning doesn't), unlike the other three groups where the shared
name is generic/DSP-accurate and the field semantics genuinely agree across
every indicator that uses the struct.

`scripts/metadata_overlay.json` already carries a note about this
(`"ttm_squeeze"._note`: *"PyO3 binding reuses the generic
SuperTrendResult{value,direction} wrapper; direction is an int (0/1) cast
from a bool, not the semantic is_squeezed flag name."*) — that note is now
stale after this fix and should be removed/updated by whoever owns that file
(out of scope for this change per the task's scope guard).

## Judgment: (a) small fix, not (b) broad refactor

Only **one** of the four shared-wrapper groups was a genuine semantic
mismatch; the other three (`CyberCycleResult`, `PhasorResult`,
`TrendRocResult`) are deliberate, semantically-clean reuse of a generic
shape/name across a small family of closely-related DSP indicators, and
touching those would be a judgment call with no real bug to justify it.
Fixing all of it broadly would mean renaming public API classes
(`PhasorResult` is used by 4 indicators, `CyberCycleResult`/`TrendRocResult`
by 2 each) for no debuggability gain — this is the "pervasive, don't rush a
broad rename" case for those three.

The `TtmSqueeze`/`SuperTrendResult` case, however, was small and isolated:
one macro invocation, one new struct definition, one new `add_class`
registration. It required no changes to field access, tuple/attribute
patterns, or the values callers already read (`res.value`, `res.direction`
still exist, just now on an honestly-named class), and public API impact is
purely additive: `TtmSqueezeResult` is a new exported PyO3 class,
`SuperTrendResult` is untouched and still means what it always meant for
`SuperTrend`. This is the "small, safe, low-risk" case, so it was implemented
directly per the task's guidance.

## What was changed

In `quantwave-py/src/indicators.rs`:

1. Added a new `TtmSqueezeResult` struct (`value: f64, direction: i8`) —
   structurally a clone of `SuperTrendResult` but with its own honest name.
2. Changed the `TtmSqueeze` macro invocation
   (`export_ohlc_in_record_out!`) to build and return `TtmSqueezeResult`
   instead of `SuperTrendResult`.
3. Registered the new class with `m.add_class::<TtmSqueezeResult>()` in
   `register()`.

No other file needed changes — `results.py`'s resilient-import list and the
`.pyi` stub do not reference `SuperTrendResult`/`TtmSqueeze` specifically, and
a grep of `quantwave-py/python/` and `tests/python/` found no
`isinstance()`/`type().__name__` checks against any of the shared wrapper
class names, so nothing else depends on the old (mis)naming.

## Not changed (documented only, per scope guard and the (b) judgment)

- `CyberCycleResult` (shared by `CyberCycle`, `ChannelCycle`)
- `PhasorResult` (shared by `Phasor`, `CorrelationCycle`, `SineWave`,
  `HtPhasor`)
- `TrendRocResult` (shared by `PrecisionTrend`, `ReversionIndex`)

These are all shape- and semantics-clean; recommend leaving as-is unless a
future issue specifically wants uniquely-named wrapper classes for every
indicator regardless of semantic risk, in which case it should be scoped as
its own follow-up (touches multiple public PyO3 classes, `results.py`'s
resilient-import list, and any downstream code doing
`isinstance()`/`type().__name__` checks — none found today, but that should
be re-verified at the time).

## Verification performed

- `./scripts/rustfmt_check.sh` — clean.
- `cargo clippy -p quantwave-core -p quantwave-polars -p quantwave-backtest --all-targets -- -D warnings` — no issues.
- `cargo clippy -p quantwave-py --all-targets -- -D warnings` — pre-existing warnings only, none on the changed lines; no new warnings introduced.
- `cargo test -p quantwave-core` — 897 passed.
- `cargo build -p quantwave-py` — 0 errors.
- `maturin develop --release --manifest-path quantwave-py/Cargo.toml` (built into a scratch venv) — succeeded.
- Confirmed at runtime: `type(qw._quantwave.SuperTrend(10, 3.0).next(1,1,1)).__name__ == "SuperTrendResult"` and `type(qw._quantwave.TtmSqueeze(20, 2.0, 1.5).next(1,1,1)).__name__ == "TtmSqueezeResult"`.
- `python3 -m pytest tests/python/ -k "ttm_squeeze or supertrend or super_trend"` — 6 passed.
- `python3 -m pytest tests/python/ --ignore=tests/python/test_benchmark_harness.py` (full suite; that one file fails to collect in this environment for an unrelated `ModuleNotFoundError: benchmarks`, pre-existing) — 533 passed, 0 failed, 3 skipped.
