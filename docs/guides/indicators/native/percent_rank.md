# Percent Rank

<div class="indicator-meta"><span class="category-badge">Statistics</span> <span class="kw-badge">statistics</span> <span class="kw-badge">rank</span> <span class="kw-badge">percentile</span> <span class="kw-badge">normalization</span></div>

Where the current value sits inside its own trailing window, as the fraction of window values less than or equal to it.

## Visual Example

> **Chart**: Sparkline or annotated price series showing **Percent Rank** behaviour on synthetic trending + cyclic data. Run `python docs/gen_indicator_previews.py --only percent_rank` after extending the generator.

*Visual placeholder — standards bulk upgrade 2026-10-02 IST. Core logic in `series_norm`.*

## Description

Where the current value sits inside its own trailing window, as the fraction of window values less than or equal to it.

Rank a series against its own history before comparing years. A daily chain gextotal column uses period 252. The rank is not a signal by itself; compare it with a threshold in the caller.

Native Rust implementation with gold-standard or TA-Lib parity tests where applicable.

Not an Ehlers filter. Empirical percent rank of a trailing window, including the current observation.

**Typical applications:**

- See Parameters — default period/length `252`
- Validated via proptests and gold-standard vectors where available
- Use Polars `.ta` plugins for batch; `streaming_class()` for live

QuantWave implements this via the universal `Next<T>` trait — bit-identical across Rust streaming, Python streaming, and Polars `.ta()` batch plugins.

## Formula / Specification

**Implementation** (`series_norm`):

\mathrm{percent\_rank}_t = \frac{\#\{x_i \le x_t : i \in [t-n+1, t]\}}{n}


## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `period` | 252 | Trailing window length, in bars. 252 is one trading year of daily data. |


## Usage Examples

**Streaming (Rust)**

```rust
use quantwave_core::indicators::PercentRank;
use quantwave_core::traits::Next;

let mut ind = PercentRank::new(252);
for price in &prices {
    let value = ind.next(price);
}
```

**Streaming (Python)**

```python
from quantwave import PercentRank

ind = PercentRank(252)
for price in prices:
    value = ind.next(price)
```

**Polars Batch (Python)**

```python
import polars as pl
import quantwave as qw

def apply_percent_rank(series: pl.Series) -> pl.Series:
    ind = qw.PercentRank(252)
    return pl.Series([ind.next(float(v)) for v in series.to_list()])

df = (
    pl.read_csv('ohlcv.csv')
    .lazy()
    .with_columns(
        pl.col("close").map_batches(apply_percent_rank, return_dtype=pl.Float64).alias("percent_rank")
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

**Primary Source**: Standard trailing percent rank. Window and 0.90 / 0.10 thresholds follow the gamma-exposure normalization in David Bergstrom, Build Alpha, Gamma Exposure (Sep 2026).

**Implementation**: `quantwave-core/src/indicators/series_norm` (`PercentRank` / `_METADATA`).

**Provenance**: Standards bulk upgrade 2026-10-02 IST — see `docs/DOCUMENTATION_STANDARDS.md`.
