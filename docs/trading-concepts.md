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
- **Trading session.** One day the exchange is open, from the opening bell (9:30am ET)
  to the closing bell (4pm ET, 1pm on early-close days such as the day after
  Thanksgiving). Daily bars are one per session.
- **Exchange calendar.** The official list of sessions. NYSE (code XNYS) closes on
  about nine holidays a year, including Good Friday, which isn't a federal holiday, and
  on rare one-off days such as Hurricane Sandy (2012-10-29/30). Nasdaq-listed stocks
  like GOOG, META and AMZN trade the same sessions.
- **Partial bar.** During market hours a data source shows today's bar as it forms. Its
  "close" is just the latest trade and changes until 4pm, so it isn't stored.
- **Dividend.** Cash the company pays per share. On the *ex-dividend date* the share
  price typically drops by about the dividend amount, since new buyers no longer get it.
  Adjusted close removes that drop so it doesn't look like a loss.
- **Back-adjustment / restatement.** When a split or dividend happens, the data
  provider re-scales *all earlier* adjusted prices so the series stays continuous.
  History you downloaded last month can therefore differ from the same history today.
  That's why incremental updates check for it.
- **Yahoo's Close vs Adj Close.** Yahoo's Close is already adjusted for splits but not
  dividends. Adj Close is adjusted for both. Truly raw prices (what the ticker showed
  on the day) aren't available from this source.
- **Large one-day move.** Single-day moves above 25% are rare for large companies but
  real, usually around earnings reports. META fell 26% on 2022-02-03 after weak
  guidance. They're flagged for a look, not deleted.

<!-- Phases 2–5 add indicators, signals, backtest metrics and ML evaluation terms. -->
