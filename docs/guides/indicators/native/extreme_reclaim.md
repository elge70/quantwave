# Extreme Reclaim

<div class="indicator-meta"><span class="category-badge">Price Action</span> <span class="kw-badge">price-action</span> <span class="kw-badge">reclaim</span> <span class="kw-badge">false-break</span> <span class="kw-badge">atr</span></div>

Prior N-bar high or low is pierced and the close finishes back inside, with penetration at least k times Wilder ATR.

## Visual Example

> **Chart**: Sparkline or annotated price series showing **Extreme Reclaim** behaviour on synthetic trending + cyclic data. Run `python docs/gen_indicator_previews.py --only extreme_reclaim` after extending the generator.

*Visual placeholder — standards bulk upgrade 2026-10-02 IST. Core logic in `market_structure`.*

## Description

Prior N-bar high or low is pierced and the close finishes back inside, with penetration at least k times Wilder ATR.

bullish is the full three-part test. bull_pierce and bull_reclaim are the parts, so a caller can drop the size filter. A close that stays beyond the extreme is a break, not a reclaim.

Price-action tooling with streaming and Polars batch parity. Rich outputs feed backtest signals, regime filters, and ML feature pipelines.

Not Ehlers. Pierce-and-reclaim from Build Alpha CustomIndicators.xml (Bergstrom): window 20, ATR 20, k = 0.5, penetration compared with >=.

**Typical applications:**

- Size stops and position risk from band width or ATR expansion
- Detect squeeze conditions (narrow bands) before breakout systems
- Warm-up: first `20` bars build rolling volatility state
- Combine with trend direction (SuperTrend, MACD) for breakout bias

QuantWave implements this via the universal `Next<T>` trait — bit-identical across Rust streaming, Python streaming, and Polars `.ta()` batch plugins.

## Formula / Specification

**Implementation** (`market_structure`):

\text{bull}: low_0 \le \min(low)_{1..N},\ close_0 > \min(low)_{1..N},\ \min(low)-low_0 \ge k\cdot ATR


## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `window` | 20 | Bars in the prior extreme. The current bar is excluded. |
| `atr_period` | 20 | Wilder ATR length for the penetration test. |
| `size_k` | 0.5 | Minimum penetration as a multiple of ATR. |


## Usage Examples

**Streaming (Rust)**

```rust
use quantwave_core::indicators::ExtremeReclaim;
use quantwave_core::traits::Next;

let mut ind = ExtremeReclaim::new(20);
for price in &prices {
    let value = ind.next(price);
}
```

**Streaming (Python)**

```python
from quantwave import ExtremeReclaim

ind = ExtremeReclaim(20)
for price in prices:
    value = ind.next(price)
```

**Polars Batch (Python)**

```python
import polars as pl
import quantwave as qw

def apply_extreme_reclaim(series: pl.Series) -> pl.Series:
    ind = qw.ExtremeReclaim(20)
    return pl.Series([ind.next(float(v)) for v in series.to_list()])

df = (
    pl.read_csv('ohlcv.csv')
    .lazy()
    .with_columns(
        pl.col("close").map_batches(apply_extreme_reclaim, return_dtype=pl.Float64).alias("extreme_reclaim")
    )
    .collect()
)
```

All surfaces are bit-identical via the single `Next<T>` implementation and proptests.

## Edge Cases & Limitations

- Warm-up: first `20` bars may return NaN or partial state per implementation.
- Parameter sensitivity: smaller periods increase noise; larger periods increase lag.
- Sudden gaps or bad ticks can distort rolling windows — consider pre-filtering.
- Single-series indicators ignore volume unless otherwise documented.
- Validated via proptests against gold-standard vectors where available.
- No look-ahead bias; streaming and Polars batch paths are bit-identical.

## Boundary Behavior

| Condition | Behavior |
|-----------|----------|
| Warm-up | Early bars return empty event lists or default structs (no scalar NaN). |
| period > len | Insufficient history yields no events rather than NaN scalars. |
| NaN inputs | NaN OHLC typically suppresses event detection for that bar. |
| Invalid params | Invalid swing_strength or tolerance raises ValueError. |
| Empty data | Empty input returns empty event collections. |

## Related Indicators & See Also

- [Indicator Gallery](../gallery.md)
- [Native Indicators index](index.md)
- [Batch vs Streaming guide](../../../examples/batch-streaming.md)
- [RSI](relative_strength_index_rsi.md)
- [SuperTrend](../supertrend/)

## Sources & References

**Primary Source**: David Bergstrom, Build Alpha, https://www.buildalpha.com/backtest-ict-and-smc/ CustomIndicators.xml (window 20, ATR length 20, k = 0.5).

**Implementation**: `quantwave-core/src/indicators/market_structure` (`ExtremeReclaim` / `_METADATA`).

**Provenance**: Standards bulk upgrade 2026-10-02 IST — see `docs/DOCUMENTATION_STANDARDS.md`.
