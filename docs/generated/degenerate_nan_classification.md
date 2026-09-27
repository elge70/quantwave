# Degenerate-Input NaN/Inf Classification (Phase 0 judgment pass)

Classifies the 90 (indicator, scenario, output_field) finding-groups from
`docs/generated/degenerate_nan_audit.json` (produced by
`scripts/audit_degenerate_nan.py`) into the 3-pattern menu from the design
notes of `quantwave-1jqv`:

- **(a) GUARDABLE-WITH-DOMAIN-DEFAULT** — genuine singularity, sensible
  domain-correct answer exists.
- **(b) GENUINE SINGULARITY, NO SENSIBLE DEFAULT** — mathematically
  undefined for this input, no domain convention to fall back on. Noted as
  either "document and leave alone" (pattern 3) or "should raise instead"
  (pattern 2, caller mistake).
- **(c) UNREACHABLE IN PRACTICE** — the scenario cannot arise from real
  OHLCV data reaching this code path, or is an artifact of the fuzz
  harness's own construction, not a real production concern.

`mama`'s single finding is a Rust panic, already spun out as its own P1
(`quantwave-j3e1`) per the issue notes; it is out of scope here and untouched.

## Harness artifacts found during this pass (read before the per-indicator
tables below — they explain a large fraction of the 90)

1. **`minimal_length` scenario mislabels in-warmup NaN as "post-warmup".**
   The harness builds a series of length `n = max(warmup, 1)` and then
   forces `eff_warmup = 0` for this one scenario (`audit_degenerate_nan.py`
   line ~431), so every bar an indicator is *legitimately* still warming up
   on gets flagged as a "post-warmup" finding. This is not a math bug in any
   of the affected indicators — confirmed by reading their warmup logic
   directly (e.g. `rsi.rs`'s `warmup_changes < period` gate, `dmi.rs`'s
   `bar < period` gate). Every `minimal_length` finding below is bucket (c).

2. **Several `constant_price`/`flat_then_spike`/`all_zero` findings are
   warmup-*metadata* mismatches, not degenerate math.** For `dema`, `macd`,
   `t3`, `sar`, `stoch`, `ht_dcphase`, `ht_sine`, `ht_trendmode`, the
   `(first_bad_index, bars_bad_post_warmup)` pair is byte-for-byte identical
   across `constant_price` (flat forever), `flat_then_spike` (flat + one
   real spike), and `all_zero` (different numeric scale entirely) — three
   scenarios with genuinely different data shapes. A real division-by-zero
   singularity would differ across them; identical results across
   differently-shaped data is the signature of the harness's *warmup guess*
   (from `_metadata_generated.py` / `build_kwargs`) being shorter than the
   indicator's *true* internal warmup (e.g. `DEMA`'s true warmup is
   `2*(period-1)` from chaining two `TalibEma` lookbacks, confirmed by
   reading `incremental/dema.rs` and `incremental/talib_ema.rs`). This ties
   directly to the separately-tracked `quantwave-lt3t` metadata-reliability
   bug. Bucket (c).

3. **`frac_diff`'s findings are a harness scale artifact.** `FracDiff::new(d=0.4,
   threshold=1e-5)` (the audit's bespoke constructor) produces a weight
   vector of length **1458** (verified by running `frac_diff_weights(0.4,
   1e-5)` directly) — far longer than the harness's fixed `N=250`-bar test
   series. The window never fills within the test length, so every scenario
   shows NaN for the entire 250 bars. This is not reachable in real usage at
   this `(d, threshold)` pair with any series `>=1458` bars, and `frac_diff.rs`
   already has the correct guards (`input.is_nan()` early-return, warmup NaN
   while `window.len() < w_len`). Bucket (c).

## Guard implemented this pass

### `sma` (Classic) — bucket (a), IMPLEMENTED

- **Scenario**: `nan_passthrough`. **File**: `quantwave-core/src/indicators/smoothing.rs`, `SMA::next`.
- **Before**: a single NaN sample entering the rolling sum via `sum += input`
  poisoned `sum` forever, because `sum -= oldest` when the NaN aged out of
  the window still computes `NaN - NaN = NaN`* — the running sum, and every
  bar's output, stayed NaN for the rest of the series (250-bar test:
  `bars_bad_post_warmup=150`, `recovered_before_series_end=False`).
  *(more precisely: once the sum is NaN, every subsequent `+=`/`-=` keeps it NaN
  regardless of what ages in or out)*.
- **Domain-correct value**: SMA is genuinely undefined *while* the bad
  sample is inside the window (correctly NaN) but becomes well-defined again
  the instant the bad sample ages out — the window itself, at that point,
  contains only clean numbers, so the "default" here isn't a guess, it's
  the literal true value of `sum(window) / period`. This is the same
  reasoning already applied to `WMA` in the very same file, which recomputes
  its weighted sum from the window on every call and therefore never has
  this bug.
- **Fix**: after the incremental update, if `sum.is_nan() || sum.is_infinite()`,
  recompute `sum` directly from the window (`self.window.iter().sum()`).
  Zero cost on the clean-data path (branch never taken); O(period) only in
  the already-degenerate case.
- **Test**: `test_sma_self_heals_after_nan_ages_out_of_window` in the same
  file — asserts NaN while the bad sample is in a period-3 window, and a
  correct recovered value (`5.0` for window `[4,5,6]`) once it ages out.
- **Verification**: fresh `python3 scripts/audit_degenerate_nan.py` run
  (after `maturin develop --release`) shows `sma`'s `nan_passthrough` finding
  changed from `bars_bad_post_warmup=150, recovered=False` to
  `bars_bad_post_warmup=14, recovered=True` (heals in exactly one
  `period=14` window cycle, as expected).
- **Confidence**: high. This is the exact bug the issue names by name
  ("plain `sma`... because rolling-sum implementations do `sum -= oldest_value`").

### `rsi` (Classic) — bucket (a), ALREADY IMPLEMENTED (no change needed)

- **Scenario**: n/a (not itself a current finding for this reason — checked
  because it's the issue's own canonical example).
- **File**: `quantwave-core/src/indicators/incremental/rsi.rs`, `rsi_from_avgs`.
- Already contains exactly the guard the issue describes: `if avg_loss ==
  0.0 { 100.0 } else { ... }`, matching TA-Lib's `ta_RSI.c` exact-zero test
  and RSI's well-known asymptotic value. No action needed — confirmed
  present, not re-implemented.
- RSI *does* still have a separate, real `nan_passthrough` finding (see
  below) — that is a different bug (Wilder-average poisoning), not the
  avg-loss-zero singularity, and is classified separately in bucket (b).

## Per-indicator classification

Grouped by category. Multiple scenarios/fields on one indicator sharing a
classification and reasoning are collapsed into one entry.

### Classic

| Indicator | Scenario(s) | Bucket | Justification |
|---|---|---|---|
| `ad` | nan_passthrough | (b), document | `ad.rs`'s accumulation/distribution line is an unbounded running total since dataset start with no reset primitive (unlike `vwap`'s `anchor` flag). A NaN tick poisons the cumulative sum forever by the same `+=`-propagation math as any running sum with no window to age out of. There is no domain-correct "restart value" for a running total — recommend documenting NaN-until-restart behavior; a real fix (adding a reset/anchor concept) is a larger design change than a guard, left as follow-up. |
| `adosc` | minimal_length | (c) | Harness artifact #1. |
| `adosc` | nan_passthrough | (b), document | AD-oscillator = EMA(AD,fast) − EMA(AD,slow); inherits `ad`'s unbounded-accumulator poisoning plus EMA's infinite-memory recursion on top. Same reasoning as `ad`/`ema`. |
| `adx` | minimal_length | (c) | Harness artifact #1. |
| `adx` | constant_price, flat_then_spike, all_zero | (b), **real bug, worth a follow-up fix (not implemented)** | Read `incremental/dmi.rs`'s `DmiCore::step`. On a zero-true-range period (flat OHLC), `sum_tr` never exceeds `0.0`, so `step` returns `None` for every bar and `ADX::next`'s seeding logic (`self.dx_values.push(dx)` / `adx_ready=true`) never executes — **even after real volatility resumes** (as in `flat_then_spike`, where recovery never happens by end-of-series despite a real price spike at bar 200). This is a genuine implementation defect (permanent seed failure), not a math singularity with a clean default — a limit-locked stock, a pegged FX pair, or a thin holiday session can produce a real zero-true-range stretch. Fixing it means reworking `DmiCore`'s seed/reseed state machine (also touches `DX`/`PLUS_DI`/`MINUS_DI`/`ADXR`), which is nontrivial and risks behavior changes without a dedicated test pass — left as a documented, higher-priority follow-up rather than rushed here. |
| `adx` | zero_range_ohlc, nan_passthrough (`value`/`dx`) | (c), harness/incidental | These *look* like recovery but it's via a floating-point quirk, not a guard: once `sum_tr` is poisoned, `pdi`/`mdi` become NaN, `sum_di = pdi+mdi` is NaN, and the comparison `sum_di > 0.0` is *false* for NaN (IEEE-754), silently falling to the `else { 0.0 }` branch and handing `dx=0.0` (a real number) back into the `ADX` Wilder average, which then decays the contamination out over one `period`. Not a deliberate fix; noted for awareness only, no action taken. |
| `alligator` | minimal_length | (c) | Harness artifact #1. |
| `alligator` | nan_passthrough (lips/jaw/teeth) | (b), document | `alligator.rs`'s `SmmaOffset` keeps `prev_smma: Option<f64>` — a Wilder-style recursive average with the exact same infinite-memory poisoning shape as EMA. The `history` `VecDeque` used for the offset/shift is a buffer of *already-computed* (and now poisoned) SMMA values, not raw inputs, so it cannot self-heal the way `SMA`'s window-of-raw-inputs can. |
| `alma` | nan_passthrough | (a), already correct | ALMA is a fixed-window weighted average over raw inputs; NaN is correctly undefined only while inside the window (`bars_bad=9`, recovers). No change needed. |
| `aroon` | minimal_length | (c) | Harness artifact #1. |
| `cci` | minimal_length | (c) | Harness artifact #1. |
| `dema` | minimal_length | (c) | Harness artifact #1. |
| `dema` | constant_price, flat_then_spike, all_zero, nan_passthrough | (c) | Harness artifact #2 (warmup-metadata mismatch). Confirmed by reading `incremental/dema.rs`: `DEMA` chains two `TalibEma` stages; `TalibEma::next` explicitly early-returns `f64::NAN` on `input.is_nan()` **without touching its internal `value` state**, so a NaN input bar is skipped cleanly rather than poisoning the EMA — the "recovery" seen here is really the double-EMA warmup catching back up, not NaN-recovery logic. |
| `heikin_ashi` | nan_passthrough `close` | (a), already correct | `HA_Close = (O+H+L+C)/4` is a plain per-bar average of that bar's own OHLC; recovers in 1 bar once the bad input bar passes, as expected. |
| `heikin_ashi` | nan_passthrough `open` | (b), document | `heikin_ashi.rs`: `HA_Open = (prev_HA_Open + prev_HA_Close)/2` is *defined* recursively on its own prior output — this is the textbook Heikin-Ashi formula, not an implementation choice. Once `HA_Close` goes NaN for one bar, `HA_Open` is undefined forever after by the formula's own definition. No alternate "domain-correct" value exists without redefining Heikin-Ashi; recommend documenting, not guarding. |
| `hma` | nan_passthrough | (a), already correct | Hull MA composes fixed WMA windows over raw inputs; self-heals (`bars_bad=16`). No change needed. |
| `kama` | minimal_length | (c) | Harness artifact #1. |
| `kama` | nan_passthrough | (b), document | `kama.rs` keeps `prev_kama: Option<f64>` fed back into `kama = prev + sc*(input-prev)` every bar — same infinite-memory recursive shape as EMA. Genuinely undefined forever after a bad tick; no window to recover from. |
| `keltner` | nan_passthrough (upper/middle/lower) | (b), document | `keltner.rs`'s middle band is `smoothing::EMA` on typical price, and the bands add/subtract an ATR that is itself EMA-based — both infinite-memory recursions. Same class as `ema`/`kama`. |
| `macd` | minimal_length | (c) | Harness artifact #1. |
| `macd` | constant_price, flat_then_spike, all_zero, nan_passthrough (macd/signal/histogram) | (c) | Harness artifact #2 (warmup-metadata mismatch): identical `(26,7,True)` across all three differently-shaped scenarios. `incremental/macd.rs`'s true warmup is `out_start = sp-1+signalperiod-1` (33 for defaults 12/26/9), longer than the harness's guessed `26`. Note: `MACD::update_emas` (unlike `TalibEma`) does *not* gate on `input.is_nan()`, so a genuine mid-stream bad tick (not exercised distinctly by this scenario, since it collapses into the same warmup-mismatch signature) would poison `slow_ema`/`fast_ema` permanently — flagged as a latent instance of the same systemic `nan_passthrough` risk as `ema`, worth folding into any future fix for that class, but not separately actionable from this audit's data. |
| `mom` | minimal_length | (c) | Harness artifact #1. |
| `mom` | nan_passthrough | (a), already correct | `mom = close[t] - close[t-n]`: a bad tick only contaminates the single output that directly subtracts it; recovers in 1 bar by construction. No change needed. |
| `pivot_points` | nan_passthrough (p/r1/r2/s1/s2) | (a), already correct | Classic pivots are recomputed from the *previous* bar's H/L/C only (no running state); recovers in 1 bar. No change needed. |
| `roc` | minimal_length | (c) | Harness artifact #1. |
| `roc` | nan_passthrough | (a), already correct | Same shape as `mom` (percentage version); recovers in 1 bar. No change needed. |
| `rsi` | minimal_length | (c) | Harness artifact #1. |
| `rsi` | nan_passthrough | (b), document | Separate from the (already-guarded) avg-loss-zero singularity. `incremental/rsi.rs`'s Wilder average `avg_gain = (avg_gain*(period-1)+gain)/period` is a geometric-decay recursion with infinite memory (same shape as EMA, no fixed window to age out of) — a NaN `change` poisons `avg_gain`/`avg_loss` permanently. Genuine singularity from bad input, not a caller-mistake in the zero-length-window sense; recommend documenting, same systemic class as `ema`/`kama`. |
| `sar` | constant_price, flat_then_spike, all_zero, minimal_length, nan_passthrough, zero_range_ohlc | (c) | All six scenarios show identical `(0,1,True)` — SAR only ever flags a single bar bad regardless of input shape, which is the harness's own PSAR seed-bar convention (SAR needs one prior bar to establish trend direction before it can produce a value), not a data-dependent singularity. |
| `stoch` | constant_price, flat_then_spike, all_zero, zero_range_ohlc, nan_passthrough | (c) | Harness artifact #2 (warmup-metadata mismatch) — identical `(5,3,True)` across all shape scenarios including the genuinely-varying `zero_range_ohlc`. |
| `stoch` | minimal_length | (c) | Harness artifact #1. |
| `t3` | constant_price, flat_then_spike, all_zero, nan_passthrough | (c) | Harness artifact #2 — identical `(5,19,True)` across differently-shaped scenarios; T3's real warmup (6 cascaded EMA stages) exceeds the harness's guess. |
| `t3` | minimal_length | (c) | Harness artifact #1. |
| `tema` | nan_passthrough | (b), document | Triple EMA — same infinite-memory chain reasoning as `ema`/`dema`, but (unlike `DEMA`'s `TalibEma`-based implementation) `tema.rs`'s own EMA stages do not gate on NaN input, so it does not get `DEMA`'s incidental self-heal. Genuine poisoning, recommend documenting. |
| `ttm_squeeze` | nan_passthrough | (b), document | Composite of Bollinger Bands (`SMA`-based, would now self-heal after this pass's fix) and Keltner Channels (EMA-based, does not). The EMA half dominates the failure mode; net effect is still infinite-memory poisoning. Document, same class. |
| `vwap` | nan_passthrough | (a), already correct (harness didn't exercise the design's own reset) | `vwap.rs`'s `AnchoredVWAP` accumulates `cumulative_tp_v`/`cumulative_v` since the last `anchor=true` bar — genuinely unbounded memory *between* anchors, so a NaN tick poisons the VWAP for the rest of the current session, exactly as expected. But the audit's `_fill()` helper always sets `'anchor': [False]*n` (never exercises a reset), so the harness cannot observe VWAP's actual, already-correct recovery mechanism: the next `anchor=true` bar unconditionally resets both accumulators (`self.cumulative_tp_v = price*volume`), clearing any NaN contamination immediately. No code change needed; worth noting in the harness's own follow-up that `applicable_scenarios` should also test a mid-series NaN-then-anchor sequence for indicators with an `anchor` input, to distinguish this from indicators (`ad`) that have no such reset at all. |
| `willr` | minimal_length | (c) | Harness artifact #1. |
| `willr` | nan_passthrough | (a), already correct | Fixed lookback extremum over a window of raw inputs; recovers in 1 bar as the bad tick ages out of the max/min window. No change needed. |
| `wma` | nan_passthrough | (a), already correct | `smoothing::WMA` already recomputes its weighted sum from the window on every call (the exact pattern this pass added to `SMA`); self-heals after `period=14` bars. No change needed — this is the reference implementation `SMA`'s fix now matches. |

### Ehlers DSP

All entries below whose only finding is `nan_passthrough` with
`recovered_before_series_end=False` share one root cause, verified by
reading representative source files directly (`bandpass.rs`, `super_smoother.rs`,
`high_pass.rs`, and cross-checked structurally via `grep` for persistent
`_prev`/`history[N]` scalar state across the remaining files in this list):
these are second-order (or higher) **recursive IIR difference-equation
filters** in the Ehlers "Cybernetic Analysis for Stocks and Futures" design
tradition — e.g. `SuperSmoother`'s `res = c1*(input+price_prev)/2 +
c2*ss_history[0] + c3*ss_history[1]`, `BandPass`'s `bp =
0.5*(1-alpha)*(input-price_prev2) + beta*(1+alpha)*bp_history[0] -
alpha*bp_history[1]`. These carry **infinite memory by design** (that's
what makes them IIR filters, as opposed to the FIR/window-based `SMA`/`WMA`
this pass fixed) — a NaN sample entering `self.*_history[]` or
`self.price_prev*` propagates through every subsequent recursive step
exactly like `EMA`, with no finite window to age it out of. This is **bucket
(b)**, genuine singularity from bad input, no domain-correct substitute
value exists (there's no equivalent of "RSI=100" for "what should a 2-pole
Butterworth filter output when its own last two outputs are NaN"); the
systemic, correct fix is an input-sanitization decision at the streaming
`.next()` boundary (skip-and-hold or reject NaN before it ever reaches
indicator state), which is explicitly out of scope for a per-indicator
guard pass and is the same "worth a bigger follow-up" note the issue itself
flags for `sma`/`ema`-class poisoning.

Applies to (all: scenario `nan_passthrough`, bucket (b), document/follow-up
as above): `bandpass`, `butterworth2`, `butterworth3`, `channel_cycle` (trigger+value),
`classic_laguerre`, `continuation_index`, `cyber_cycle` (trigger+value),
`cybernetic_oscillator`, `cycle_trend_analytics` (trend+cycle), `dsma`,
`emd` (trend), `fisher_high_pass`, `fm_demodulator`, `fourier_series_model`,
`frama`, `gaussian_filter`, `generalized_laguerre`, `griffiths_predictor`,
`high_pass`, `homodyne_discriminator`, `kalman_filter` (Kalman gain/state
update is itself a recursive estimator — same class), `laguerre_filter`,
`laguerre_oscillator`, `laguerre_rsi`, `mad`, `mesa_stochastic`,
`one_euro_filter`, `recursive_median`, `recursive_median_oscillator`,
`reversion_index` (roc+trend), `roofing_filter`, `simple_predictor`,
`super_smoother`, `swiss_army_knife`, `ultimate_bands` (upper/middle/lower),
`ultimate_channel` (center/upper/lower), `ultimate_smoother`,
`universal_oscillator`, `voss_predictor` (filt+voss), `wavetrend` (wt1+wt2),
`zero_lag` (trigger+value).

Two indicators in this category have a window buffer *containing
already-recursively-computed values* rather than raw inputs (`my_rsi.rs`,
`mesa_stochastic.rs`, `dsma.rs`, etc. hold `VecDeque`s of filtered output,
not price) — confirmed this does **not** grant the `SMA`-style self-heal,
because the buffered values themselves are permanently NaN once the
upstream recursive stage is poisoned; still bucket (b), no distinct action.

Remaining Ehlers DSP entries with different, non-`nan_passthrough`-only
signatures:

| Indicator | Scenario(s) | Bucket | Justification |
|---|---|---|---|
| `cg` | nan_passthrough | (a), already correct | Center-of-gravity is a fixed-window weighted average over raw inputs (FIR, not IIR); self-heals in 10 bars. No change needed. |
| `ehlers_filter` | nan_passthrough | (a), already correct | Self-heals in 29 bars — fixed-window design; no change needed. |
| `ehlers_stochastic` | nan_passthrough | (a), already correct | Self-heals in 18 bars; no change needed. |
| `fisher` | nan_passthrough | (a), already correct | Self-heals in 1 bar — the Fisher transform here is applied to a windowed min/max normalization of raw price, not chained onto its own prior output. No change needed. |
| `hamming_filter`, `hann_filter`, `triangle_filter` | nan_passthrough | (a), already correct | FIR window filters (explicit tapered-weight sums over a fixed window of raw inputs, analogous to `WMA`); self-heal in ~20 bars each. No change needed. |
| `ht_dcperiod` | minimal_length | (c) | Harness artifact #1. |
| `ht_dcperiod` | nan_passthrough | (b), document | Hilbert-transform-based dominant cycle period; the Hilbert transformer and its smoothing stages are IIR-recursive over many bars. Same class as the bulk list above. |
| `ht_dcphase` | constant_price, flat_then_spike, all_zero, minimal_length, nan_passthrough | (c) | Harness artifact #2 — identical `(50,13,True)` across all shape scenarios (real internal Hilbert-transform warmup exceeds harness guess). |
| `ht_phasor` | minimal_length | (c) | Harness artifact #1. |
| `ht_phasor` | nan_passthrough (in_phase/quadrature) | (b), document | Hilbert transformer's in-phase/quadrature components are IIR-recursive (unlike `phasor`/`sine_wave`'s simpler construction below); genuinely poisoned, no fixed window. |
| `ht_sine` | constant_price, flat_then_spike, all_zero, minimal_length, nan_passthrough (sine/leadsine) | (c) | Harness artifact #2/#1 — identical values across shape scenarios, same Hilbert-transform warmup mismatch as `ht_dcphase`. |
| `ht_trendmode` | constant_price, flat_then_spike, all_zero, minimal_length, nan_passthrough | (c) | Same as `ht_dcphase`/`ht_sine`. |
| `hurst_exponent` | minimal_length | (c) | Harness artifact #1. |
| `hurst_exponent` | nan_passthrough | (a), already correct | Rolling R/S-statistic over a long fixed window of raw inputs; self-heals once the window fully cycles (`bars_bad=100`, consistent with a ~100-bar analysis window). No change needed. |
| `inverse_fisher` | nan_passthrough | (a), already correct | Self-heals in 1 bar (point-wise transform of an already-windowed input); no change needed. |
| `my_rsi` | minimal_length | (c) | Harness artifact #1. |
| `my_rsi` | nan_passthrough | (b), document | Wilder-style RSI variant — infinite-memory recursive average, same reasoning as `rsi`. |
| `oc_price_rsi` | minimal_length | (c) | Harness artifact #1. |
| `oc_price_rsi` | nan_passthrough | (b), document | Same as `my_rsi`. |
| `projected_moving_average` | nan_passthrough (predict/pma) | (a), already correct | Self-heals in 20-22 bars; linear-regression-style projection over a fixed window of raw inputs. No change needed. |

### ML Features

| Indicator | Scenario(s) | Bucket | Justification |
|---|---|---|---|
| `frac_diff` | all scenarios (constant_price, flat_then_spike, all_zero, minimal_length, nan_passthrough) | (c) | Harness scale artifact #3 above — window (1458 weights at `d=0.4, threshold=1e-5`) never fills within the harness's fixed 250-bar series. `frac_diff.rs` already has correct guards (`input.is_nan()` early return, warmup-NaN while filling). Not reachable in real usage with a series `>=1458` bars at this parameter pair; would need re-testing with a longer series or larger threshold to say anything about real degenerate-math exposure, which this audit run cannot currently do. |
| `hurst_exponent` | see Ehlers DSP table above (metadata categorizes it Ehlers DSP in this build, but conceptually ML Features) | — | See above. |
| `kalman_filter` | nan_passthrough | (b), document | Kalman filter state/covariance update is a textbook recursive estimator (infinite memory by design — that's the whole point of a Kalman filter over a fixed window); a NaN observation poisons the state estimate forever with no windowed fallback. Same systemic class as the Ehlers DSP IIR filters. |

### Rocket Science

| Indicator | Scenario(s) | Bucket | Justification |
|---|---|---|---|
| `homodyne_discriminator` | nan_passthrough | (b), document | Homodyne discriminator (Hilbert-transform-based cycle measurement) is IIR-recursive; same class as `ht_dcperiod`/`ht_phasor`. |
| `phasor` | nan_passthrough (in_phase/quadrature) | (a), already correct | Self-heals in 3 bars — simpler, more locally-windowed construction than `ht_phasor`'s full Hilbert transformer (confirmed by the much shorter recovery time: 3 bars vs. permanent for `ht_phasor`). No change needed. |
| `sine_wave` | nan_passthrough (in_phase/quadrature) | (a), already correct | Same as `phasor`; self-heals in 3 bars. No change needed. |

### Modern

| Indicator | Scenario(s) | Bucket | Justification |
|---|---|---|---|
| `stc` | nan_passthrough | (b), document | Schaff Trend Cycle is a stochastic-of-MACD-of-EMA construction; inherits EMA's infinite-memory poisoning at its base. Same systemic class. |

## Summary counts

- **Total finding-groups classified**: 195 (across 90 indicators; `mama`'s
  panic finding excluded as an already-tracked separate P1, `quantwave-j3e1`).
- **Bucket (a) — guardable / already domain-correct**: majority of these are
  "already correct, no code change needed" (self-healing FIR/fixed-window
  or per-bar-recomputed designs: `alma`, `hma`, `wma`, `mom`, `roc`, `willr`,
  `pivot_points`, `heikin_ashi.close`, `vwap`, `cg`, `ehlers_filter`,
  `ehlers_stochastic`, `fisher`, `hamming_filter`, `hann_filter`,
  `triangle_filter`, `hurst_exponent`, `inverse_fisher`,
  `projected_moving_average`, `phasor`, `sine_wave`, plus the pre-existing
  `rsi` avg-loss-zero guard). One indicator — **`sma`** — got an actual new
  guard implemented this pass. Roughly 22-23 finding-groups land here.
- **Bucket (b) — genuine singularity, no sensible default**: the large
  majority of the remaining findings (the entire Ehlers DSP recursive/IIR
  filter family, `ema`/`kama`/`keltner`/`rsi`(nan_passthrough)/`tema`/
  `ttm_squeeze`/`stc`/`kalman_filter`/`homodyne_discriminator`/`ad`/`adosc`/
  `alligator`/`heikin_ashi.open`/`my_rsi`/`oc_price_rsi`, plus `adx`'s
  zero-true-range permanent-stall defect). All documented as "NaN is
  genuinely undefined here, no per-indicator guard exists" with the
  systemic follow-up (input sanitization at the streaming boundary,
  explicitly out of scope for this pass) noted once rather than repeated 50
  times. Roughly 60-65 finding-groups land here. None implemented as
  raise-on-caller-mistake changes in this pass (see Deliverable 3 below).
- **Bucket (c) — unreachable / harness artifact**: `minimal_length`
  mislabeling (harness artifact #1, ~20 indicators), warmup-metadata
  mismatches (harness artifact #2: `dema`, `macd`, `t3`, `sar`, `stoch`,
  `ht_dcphase`, `ht_sine`, `ht_trendmode`), and `frac_diff`'s scale artifact
  (#3). Roughly 45-50 finding-groups land here.

(Exact per-finding bucket is in the tables above; the ranges here reflect
that several indicators have multiple scenario/field rows that were
collapsed into one classification line.)

## Deliverable 3 — bucket (b) caller-mistake follow-up worth raising as an error

None of the bucket (b) findings in this set are "caller passed a
structurally invalid construction argument" (e.g. a zero-length window)
in the way the issue's pattern-2 example describes — the audit's
`could_not_instantiate` list (95 indicators, tracked separately) is where
that kind of bad-constructor-argument problem actually shows up, not here.
Every finding in this set is instead "a normally-valid indicator received
one bad *data* sample mid-stream" (`nan_passthrough`) or "a normally-valid
indicator saw a real market condition (flat/zero-range prices) it can't
recover from" (`adx`). The natural fix for the former is systemic input
validation at the streaming `.next()` boundary (reject or skip-and-hold a
NaN observation before it reaches any indicator's internal state) rather
than 50+ per-indicator raises — this is exactly the "bigger, separate
design decision" the task instructions call out, and is left as a
documented follow-up, not implemented here. `adx`'s permanent-seed-failure
is a genuine implementation defect worth its own follow-up ticket
(reseed `DmiCore` after a zero-true-range stretch ends), also not
implemented here per the conservatism instruction.

## Verification

- `cargo test -p quantwave-core smoothing::` — 4 passed (including new
  `test_sma_self_heals_after_nan_ages_out_of_window`).
- `cargo test -p quantwave-core` (full suite) — 898 passed, 0 regressions.
- `./scripts/rustfmt_check.sh` — clean for `quantwave-core` (unrelated,
  pre-existing diffs in `quantwave-py/src/indicators.rs` and metadata
  scripts belong to concurrent work-in-progress from another agent on this
  issue's parallel "readiness as default" half, not touched here).
- `cargo clippy -p quantwave-core -p quantwave-polars -p quantwave-backtest --all-targets -- -D warnings` — no issues found.
- Rebuilt the Python extension (`maturin develop --release --manifest-path
  quantwave-py/Cargo.toml`, then verified the interpreter's installed
  `_lib.abi3.so` actually reflected the new build — the default `maturin
  develop` from the wrong working directory silently no-ops the copy step
  if `pyenv`'s active interpreter's site-packages differs from the
  in-tree `quantwave-py/python/quantwave/` path; had to `cp
  target/release/libquantwave_py.dylib` directly into the active
  interpreter's `site-packages/quantwave/_lib.abi3.so` to get a real
  rebuild picked up) and re-ran `scripts/audit_degenerate_nan.py` against a
  copy in `/tmp` (never overwrote the committed
  `docs/generated/degenerate_nan_audit.json`). Before/after for the
  implemented guard:
  - `sma` / `nan_passthrough` / `value`: before
    `bars_bad_post_warmup=150, recovered_before_series_end=false`; after
    `bars_bad_post_warmup=14, recovered_before_series_end=true`.
  - Total finding count moved from 195 (90 indicators) to 196 (91
    indicators) in the fresh run — this is **not** from the `sma` fix (which
    only changed severity, not presence/absence, since the transient NaN
    while the bad tick sits in-window is itself the correct value and is
    still technically "a finding" by the harness's field-level criteria).
    It's because the fresh run's `mama` no longer panics
    (`total_that_raised_exceptions` dropped from 1 to 0) and instead
    surfaces as a normal two-field finding — this appears to be unrelated,
    concurrent work on `quantwave-j3e1` (the separately-tracked mama panic)
    landing in the same working tree during this session; not something
    this pass touched or takes credit for.
