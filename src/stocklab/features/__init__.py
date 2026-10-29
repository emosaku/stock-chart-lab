"""Features: derived columns computed from prices.

Phase 2: technical indicators via pandas-ta (SMA/EMA, RSI, MACD, Bollinger Bands, ATR,
volume MA), written to the indicators table in long form; ``load_indicators`` returns
prices + indicators as one wide frame. Price basis: split-adjusted close/high/low
(docs/price-basis-decision.md). Phase 5 adds ML features (lagged returns
etc.) built on top. Rule: a value on day t may only use data from day t or earlier.
"""

from stocklab.features.pipeline import load_indicators, run_indicators

__all__ = ["load_indicators", "run_indicators"]
