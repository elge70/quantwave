# Price Imbalance

<div class="indicator-meta"><span class="category-badge">Price Action</span> <span class="kw-badge">price-action</span> <span class="kw-badge">imbalance</span> <span class="kw-badge">gap</span> <span class="kw-badge">atr</span></div>

Latest three-bar untraded range on each side: top, bottom, whether price has traded through the far side, and whether the gap exceeds a multiple of Wilder ATR.

## Visual Example

Bars `(high, low, close)` = `(10, 8, 9)`, `(11, 9, 10)`, `(14, 12, 13)`. The third bar's low is above the high from two bars earlier, so a bullish range opens with top 12 and bottom 10. A later bar with low 10.5 leaves it open. A later bar with low 9.5 trades through the bottom and closes it. The stored boundaries stay 12 and 10.

## Description

Latest three-bar untraded range on each side: top, bottom, whether price has traded through the far side, and whether the gap exceeds a multiple of Wilder ATR.

Read bull_open / bear_open as the range that is still unfilled, and bull_top / bull_bottom as the two prices. Break of structure stays on Market Structure; this does not emit one.

Price-action tooling with streaming and Polars batch parity. Rich outputs feed backtest signals, regime filters, and ML feature pipelines.

Not Ehlers. Three-bar range from Build Alpha CustomIndicators.xml (Bergstrom). Bull gap is strict low[0] > high[2]. Size uses Wilder ATR, length 20 in that file (the article prose says 14).

**Typical applications:**

- Size stops and position risk from band width or ATR expansion
- Detect squeeze conditions (narrow bands) before breakout systems
- Warm-up: first `20` bars build rolling volatility state
- Combine with trend direction (SuperTrend, MACD) for breakout bias

QuantWave implements this via the universal `Next<T>` trait — bit-identical across Rust streaming, Python streaming, and Polars `.ta()` batch plugins.

## Formula / Specification

**Implementation** (`market_structure`):

\[\text{bull}: low_0 > high_2,\ \text{top}=low_0,\ \text{bottom}=high_2,\ \text{size}: (top-bottom) > k\cdot ATR\]


## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `atr_period` | 20 | Wilder ATR length for the size test. |
| `size_k` | 0.5 | Minimum gap as a multiple of ATR. Bull uses >, bear uses >=, matching the source file. |


## Usage Examples

**Streaming (Rust)**

```rust
use quantwave_core::indicators::PriceImbalance;
use quantwave_core::traits::Next;

let mut ind = PriceImbalance::new(20);
for price in &prices {
    let value = ind.next(price);
}
```

**Streaming (Python)**

```python
from quantwave import PriceImbalance

ind = PriceImbalance(20)
for price in prices:
    value = ind.next(price)
```

**Polars Batch (Python)**

```python
import polars as pl
import quantwave as qw

def apply_price_imbalance(series: pl.Series) -> pl.Series:
    ind = qw.PriceImbalance(20)
    return pl.Series([ind.next(float(v)) for v in series.to_list()])

df = (
    pl.read_csv('ohlcv.csv')
    .lazy()
    .with_columns(
        pl.col("close").map_batches(apply_price_imbalance, return_dtype=pl.Float64).alias("price_imbalance")
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

**Primary Source**: David Bergstrom, Build Alpha, https://www.buildalpha.com/backtest-ict-and-smc/ CustomIndicators.xml (ATR length 20, k = 0.5; the article prose says ATR 14).

**Implementation**: `quantwave-core/src/indicators/market_structure` (`PriceImbalance` / `_METADATA`).

**Provenance**: Standards bulk upgrade 2026-10-02 IST — see `docs/DOCUMENTATION_STANDARDS.md`.
