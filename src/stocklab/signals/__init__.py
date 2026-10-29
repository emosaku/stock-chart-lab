"""Signals: rule-based buy/sell events detected from indicators.

Golden/death crosses, RSI overbought/oversold, MACD crossovers, Bollinger breakouts,
and simple support/resistance levels. Reads prices + indicators, writes one row per
event (ticker, date, signal type, direction, price) to the signals table. Phase 3.
"""

from stocklab.signals.detect import detect_signals
from stocklab.signals.pipeline import run_signals

__all__ = ["detect_signals", "run_signals"]
