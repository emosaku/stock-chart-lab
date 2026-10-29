# Phase 2: Indicators

Online version (with the GOOG chart): https://claude.ai/artifact/En7RaH76tvoaoaWUnXzxeZ

## Overview

Phase 2 adds `stocklab indicators`, which computes 16 technical indicators for every
stored trading day. That's about 190,000 rows across GOOG, META and AMZN, recomputed in
about 1 second. Every value uses only that day and earlier days. Each indicator is
checked against a plain-pandas implementation of its textbook formula; 59 tests pass,
none of them touching the network.

Latest reading, 2026-10-28 close:

| Ticker | Close | vs SMA 200 | RSI | MACD vs signal | Bollinger %B | ATR |
|---|---|---|---|---|---|---|
| GOOG | $321.89 | 5% below | 38.5 | below (−6.08 vs −3.32) | 0.19 | $7.92 |
| META | $612.49 | 3% below | 30.7 | below (−16.12 vs 0.26) | 0.00, on the lower band | $23.96 |
| AMZN | $254.60 | 5% above | 50.1 | below (−0.32 vs 0.15) | 0.47, mid-band | $6.19 |

In plain words: GOOG and META sit below their 1-year average, with momentum falling and
META's RSI near the conventional oversold line of 30. AMZN is in a mild uptrend and
mid-range. GOOG's 50-day average crossed below its 200-day on 2026-10-26 (a "death
cross"), about five months after its $399 peak on 2026-05-13. Phase 3 turns readings
like these into dated buy/sell signals.

## Indicator reference

All settings live under `indicators:` in `config/settings.yaml`. Warm-up is the number
of bars before the first value; those days are left empty, never guessed. Every value is
computed from the split-adjusted `close` (plus `high`/`low` for ATR), per
[price-basis-decision.md](price-basis-decision.md).

| Stored name | What it measures | Setting | First value on bar | How it's read |
|---|---|---|---|---|
| `sma_20`, `sma_50`, `sma_200` | Trend: plain average of the last n closes | 20 / 50 / 200 days | n | Close above SMA 200 = the classic uptrend test |
| `ema_20`, `ema_50`, `ema_200` | Trend, weighted to recent days so it turns sooner | 20 / 50 / 200 days | n | Same as SMA, reacts faster |
| `rsi` | Momentum: size of up days vs down days, 0–100 | 14 days | 15 | Above 70 overbought, below 30 oversold |
| `macd`, `macd_signal`, `macd_hist` | Momentum: 12-day EMA minus 26-day EMA, its 9-day EMA, and the gap between them | 12 / 26 / 9 | 26 (macd), 34 (signal, hist) | MACD crossing above its signal = momentum turning up |
| `bb_lower`, `bb_middle`, `bb_upper` | Volatility: 20-day SMA ± 2 standard deviations | 20 days, 2 std | 20 | Wide bands = volatile, narrow = quiet |
| `bb_pctb` | Where the close sits inside the bands | 20 days, 2 std | 20 | 0 = lower band, 1 = upper band, above 1 = breakout |
| `atr` | Volatility: typical daily move in dollars, gaps included | 14 days | 15 | Compare over time; set stop distances |
| `volume_sma` | Activity: average daily volume | 20 days | 20 | A breakout on 2× this volume is more convincing |

## Key decisions

### Long table, wide on read

`indicators` stores one row per ticker, day and indicator:
`(ticker, date, indicator, value, params)`. Changing a window in settings (SMA 20 → 30)
changes rows, not the table schema, which matters once this lives in BigQuery.
`load_indicators(store, ticker)` returns prices and indicators as one wide row per day,
the shape Phase 3 signals and the Phase 6 dashboard read. `params` (e.g. `length=14`)
records how each value was made.

### Full recompute per ticker, every run

A split restates the whole price history, and an EMA carries every earlier price inside
it, so patching only new days could leave old values on a stale basis. A full recompute
is about 1 second for all three tickers and replaces each ticker's rows in one
transaction. Correctness wins over cleverness here.

### Library pitfalls found and fixed

Each indicator is tested against a plain-pandas version of its textbook formula. That
caught these in pandas-ta 0.4.71b0:

| Issue | Effect if missed | Fix |
|---|---|---|
| Bollinger std defaults to sample (ddof=1), though its docstring says population | Bands about 2.5% too wide vs Bollinger's definition and TA-Lib | Pass `ddof=0` explicitly |
| RSI emits values from bar 2, not bar 15 | GOOG showed RSI 0 on 2010-01-05, from 1 day of data | Enforce the 14-change warm-up |
| ATR starts a bar early using a partial first true range | First ATR value understated | Start on bar 15, as TA-Lib does |
| Returns `None` when history is shorter than a window | A newly listed stock would crash the run | Skip indicators that don't fit yet |

EMA is seeded with the SMA of its first n closes, as in TA-Lib, and the tests pin that
exactly. A test also pins the first bar of every indicator, so a library upgrade that
changes warm-up gets caught.

### Other rules

- `talib=False` on every call: results never depend on whether the optional TA-Lib C
  library is installed.
- No lookahead, tested directly: values up to day t are identical whether or not later
  bars exist.
- pandas-ta moved from an optional extra into the core install, since the pipeline and
  CI now need it.

## How to run and test

```bash
stocklab ingest                     # bring prices up to date
stocklab indicators                 # recompute all indicators (~1 s)
stocklab indicators --tickers GOOG  # one ticker
pytest                              # 59 tests, no network
```

In Python, `load_indicators(get_storage(), "GOOG")` returns one row per day with prices
and all 16 indicators.
