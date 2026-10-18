"""Backtesting: "would trading this signal have made money?"

Runs each signal individually through vectorbt with fees and slippage, and compares
total return, win rate, max drawdown and Sharpe ratio against simply buying and
holding the same ticker. Trades act on the bar *after* a signal fires, never the same
bar, to avoid lookahead. Writes to backtest_results. Phase 4.
"""
