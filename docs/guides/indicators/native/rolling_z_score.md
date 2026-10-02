# Rolling Z-Score

<div class="indicator-meta"><span class="category-badge">Statistics</span> <span class="kw-badge">statistics</span> <span class="kw-badge">zscore</span> <span class="kw-badge">normalization</span></div>

How many sample standard deviations the current value is from its trailing mean.

## Visual Example

> **Chart**: Sparkline or annotated price series showing **Rolling Z-Score** behaviour on synthetic trending + cyclic data. Run `python docs/gen_indicator_previews.py --only rolling_z_score` after extending the generator.

*Visual placeholder — standards bulk upgrade 2026-10-02 IST. Core logic in `series_norm`.*

## Description

How many sample standard deviations the current value is from its trailing mean.

Normalize a drifting series. A daily chain gextotal column uses period 252. Zero variance returns NaN.

Native Rust implementation with gold-standard or TA-Lib parity tests where applicable.

Not an Ehlers filter. Rolling z-score with the sample standard deviation (n − 1).

**Typical applications:**

- See Parameters — default period/length `252`
- Validated via proptests and gold-standard vectors where available
- Use Polars `.ta` plugins for batch; `streaming_class()` for live

QuantWave implements this via the universal `Next<T>` trait — bit-identical across Rust streaming, Python streaming, and Polars `.ta()` batch plugins.

## Formula / Specification

**Implementation** (`series_norm`):

z_t = (x_t - \mu_n) / s_n,\quad s_n^2 = \sum (x_i - \mu_n)^2 / (n - 1)


## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `period` | 252 | Trailing window length, in bars. Must be at least 2. |


## Usage Examples

**Streaming (Rust)**

```rust
use quantwave_core::indicators::Zscore;
use quantwave_core::traits::Next;

let mut ind = Zscore::new(252);
for price in &prices {
    let value = ind.next(price);
}
```

**Streaming (Python)**

```python
from quantwave import Zscore

ind = Zscore(252)
for price in prices:
    value = ind.next(price)
```

**Polars Batch (Python)**

```python
import polars as pl
import quantwave as qw

def apply_rolling_z_score(series: pl.Series) -> pl.Series:
    ind = qw.Zscore(252)
    return pl.Series([ind.next(float(v)) for v in series.to_list()])

df = (
    pl.read_csv('ohlcv.csv')
    .lazy()
    .with_columns(
        pl.col("close").map_batches(apply_rolling_z_score, return_dtype=pl.Float64).alias("rolling_z_score")
    )
    .collect()
)
```

All surfaces are bit-identical via the single `Next<T>` implementation and proptests.

## Edge Cases & Limitations

- Warm-up: first `252` bars may return NaN or partial state per implementation.
- Parameter sensitivity: smaller periods increase noise; larger periods increase lag.
- Sudden gaps or bad ticks can distort rolling windows — consider pre-filtering.
- Single-series indicators ignore volume unless otherwise documented.
- Validated via proptests against gold-standard vectors where available.
- No look-ahead bias; streaming and Polars batch paths are bit-identical.

## Boundary Behavior

| Condition | Behavior |
|-----------|----------|
| Warm-up | Leading bars return NaN until warmup_bars is satisfied. |
| period > len | When period exceeds series length, output is all NaN. |
| NaN inputs | NaN in input propagates to output (NaN out). |
| Invalid params | Non-positive period or missing required params raise ValueError. |
| Empty data | Empty input returns an empty result series. |

## Related Indicators & See Also

- [Indicator Gallery](../gallery.md)
- [Native Indicators index](index.md)
- [Batch vs Streaming guide](../../../examples/batch-streaming.md)
- [RSI](relative_strength_index_rsi.md)
- [SuperTrend](../supertrend/)

## Sources & References

**Primary Source**: Standard rolling z-score. The 252-bar window and ±2 thresholds follow David Bergstrom, Build Alpha, Gamma Exposure (Sep 2026).

**Implementation**: `quantwave-core/src/indicators/series_norm` (`Zscore` / `_METADATA`).

**Provenance**: Standards bulk upgrade 2026-10-02 IST — see `docs/DOCUMENTATION_STANDARDS.md`.
