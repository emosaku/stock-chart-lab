"""Features: derived columns computed from prices.

Phase 2: technical indicators via pandas-ta (SMA/EMA, RSI, MACD, Bollinger Bands, ATR,
volume MA), written to the indicators table. Phase 5 adds ML features (lagged returns
etc.) built on top. Rule: a value on day t may only use data from day t or earlier.
"""
