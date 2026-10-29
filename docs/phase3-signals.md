# Phase 3: Signals

Online version (with the GOOG signal chart): https://claude.ai/artifact/6YkBqZGyhzTbcVQKNMSomH

## Overview

Phase 3 adds `stocklab signals`, which turns stored indicators into dated buy/sell
events. It detects 10 signal types and finds 3,057 events across GOOG, META and AMZN
since 2010, in about 0.6 s. It also stores 1,468 support/resistance levels. Every event
on day t uses only data up to t's close. 77 tests pass, none of them touching the
network.

Most recent events (GOOG): a bearish Bollinger breakdown and support breakdown on
2026-10-21, a **death cross on 2026-10-26** (the 50-day SMA fell below the 200-day for
the first time since 2025-04-08), then a bullish RSI oversold recovery on 2026-10-27.
Opposing signals days apart are normal. Signals are evidence, not instructions, and
Phase 4 measures which ones carried any edge.

## Signal catalogue

Frequency is the average per stock per year since 2010 (META since its 2012 listing).
Volume ratio is the median of that day's volume divided by the 20-day average.

| Signal | Direction | Fires on the day… | Per year | Median volume ratio |
|---|---|---|---|---|
| `golden_cross` | bullish | SMA 50 crosses above SMA 200 | 0.6 | 0.96 |
| `death_cross` | bearish | SMA 50 crosses below SMA 200 | 0.6 | 0.85 |
| `rsi_oversold_recovery` | bullish | RSI rises back above 30 | 2.3 | 1.20 |
| `rsi_overbought_reversal` | bearish | RSI falls back below 70 | 6.1 | 1.01 |
| `macd_bullish_cross` | bullish | MACD crosses above its signal line | 10.2 | 0.98 |
| `macd_bearish_cross` | bearish | MACD crosses below its signal line | 10.3 | 0.99 |
| `bb_breakout_up` | bullish | close crosses above the upper Bollinger Band | 9.3 | 1.31 |
| `bb_breakout_down` | bearish | close crosses below the lower Bollinger Band | 6.3 | 1.43 |
| `resistance_breakout` | bullish | close crosses above the latest confirmed swing high | 11.5 | 1.09 |
| `support_breakdown` | bearish | close crosses below the latest confirmed swing low | 6.7 | 1.23 |

Each row in the `signals` table holds: ticker, date, signal, direction, price (close
that day), value (the number that triggered it, e.g. RSI or the level price),
volume_ratio, and a readable detail line such as "RSI rose back above 30 to 32.5".

## Key decisions

### Signals are events, not states

A signal fires on the day a condition *starts*: a line crosses another, RSI leaves a
zone. "SMA 50 above SMA 200" is true for months; "it crossed today" happens once, and
that day is what a trading rule acts on. The shared `crossed_above` helper treats a
missing value on either day as no cross, so an indicator still warming up can never
fake one.

### RSI fires on leaving the zone, not entering it

Entering oversold (RSI below 30) during a crash can keep falling for weeks ("catching
a falling knife"). Climbing back above 30 is the first sign the selling has eased, so
that's the bullish event. Overbought is the mirror image. This is configurable later if
Phase 4 suggests the entry version works better.

### Bollinger breakouts are read as momentum

A close above the upper band is labelled bullish (momentum continues). The opposite
*mean-reversion* reading ("stretched, will snap back") is just as common in trading
literature. Rather than guess, Phase 4 measures both directions' outcomes.

### Support and resistance without lookahead

A swing high is a high that's the highest of the 5 bars on each side. That definition
needs 5 *future* bars, so a level is only released for use the day after its
`confirmed_date` (pivot + 5 sessions). A breakout needs yesterday's close at or below
the active level and today's above it. Only the most recent confirmed level of each kind
is active, and levels older than 250 sessions (about a year) expire. Levels are stored
in `price_levels` so the Phase 6 dashboard can draw them.

### Store everything, filter later

There's no cooldown, deduplication or volume filter. Whipsaws (GOOG broke support on
2026-07-17, recovered, and broke it again on 07-21) are kept. Each event carries its
`volume_ratio`, so Phase 4 can test "only on above-average volume" as a variant instead
of having it baked in here.

### Full recompute, like indicators

Signals derive from indicators that are recomputed in full, so they are too, per ticker
in one transaction, in about 0.6 s for all three.

### Testing

- Each signal type has a hand-built scenario that must fire exactly once, on the right
  bar.
- Warm-up can't create crosses.
- A level isn't usable before its confirmation date, and a breakout above an
  unconfirmed swing high doesn't count.
- Old levels expire.
- A whole-pipeline lookahead test checks that signals up to day t are identical whether
  or not later bars exist.

## Known limitations

- Support/resistance is deliberately simple: one most-recent level per side, no price
  zones, no counting of how many times a level held.
- No trend filter (e.g. "only take bullish signals above the 200-day"). That's a Phase 4
  variant.
- The directions are conventions. Nothing in this phase shows that any signal predicts
  anything.

## How to run and test

```bash
stocklab ingest && stocklab indicators   # inputs up to date
stocklab signals                         # detect all; prints counts + 10 latest
stocklab signals --tickers GOOG --recent 20
pytest                                   # 77 tests, no network
```
