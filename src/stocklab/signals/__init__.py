"""Signals: rule-based buy/sell events detected from indicators.

Golden/death crosses, RSI overbought/oversold, MACD crossovers, Bollinger breakouts,
and simple support/resistance levels. Reads prices + indicators, writes one row per
event (ticker, date, signal type, direction, price) to the signals table. Phase 3.
"""
