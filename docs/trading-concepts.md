# Trading concepts glossary

Short definitions for the trading terms used in this project. Each phase adds the terms
it introduces.

## Data (Phase 1)

- **OHLCV.** Open, High, Low, Close and Volume for one period, here one trading day.
  One row is called a *bar* or *candle*.
- **Adjusted close.** The close price corrected for later splits and dividends, so
  prices from different dates can be compared. A 20:1 split (GOOG and AMZN both did
  one in 2022) divides the raw price by 20 overnight. Without adjustment, that looks
  like a 95% crash.
- **Split.** The company divides each share into several, for example 1 into 20. The
  company's value doesn't change, but the per-share price drops by that factor.
- **Trading day.** Markets close on weekends and exchange holidays, so missing
  calendar days are expected. A *missing trading day* is a gap on a day the exchange
  was open, and that's a data-quality problem.

<!-- Phases 2–5 add indicators, signals, backtest metrics and ML evaluation terms. -->
