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

## Indicators (Phase 2)

An *indicator* is a number computed from recent bars that summarises trend, momentum,
volatility or activity. All of them here look only backwards: the value on a day uses
that day and earlier days, never later ones.

- **Warm-up period.** An indicator over n days has no value until n days of data
  exist. SMA 200 starts on the 200th bar. Those early days are left empty rather than
  filled with a guess.
- **SMA (Simple Moving Average).** The plain average of the last n closes. It smooths
  out daily noise so the trend shows. 20, 50 and 200 days are roughly a month, a
  quarter and a trading year. "Price above its 200-day average" is the classic
  definition of an uptrend.
- **EMA (Exponential Moving Average).** An average that weights recent days more
  heavily, so it turns sooner than an SMA of the same length. It's seeded with the SMA
  of its first n days, as in TA-Lib.
- **RSI (Relative Strength Index).** 0–100. It compares the size of recent up days with
  recent down days over 14 days. Above 70 is conventionally *overbought* (rose fast,
  may pause). Below 30 is *oversold*. It measures speed, not direction of the trend.
- **Wilder's smoothing.** The averaging method J. Welles Wilder used for RSI and ATR.
  It's an EMA that reacts more slowly (each day counts 1/n).
- **MACD (Moving Average Convergence Divergence).** The 12-day EMA minus the 26-day EMA:
  how far short-term momentum is running ahead of the longer trend. The *signal line*
  is a 9-day EMA of MACD. The *histogram* is MACD minus signal. MACD crossing above its
  signal is read as momentum turning up.
- **Bollinger Bands.** A 20-day SMA with bands 2 standard deviations above and below.
  The bands widen when the price is volatile and tighten when it's quiet. **%B** places
  the close inside the bands: 0 = on the lower band, 1 = on the upper, above 1 = closed
  above the upper band (a *breakout*).
- **True range / ATR (Average True Range).** True range is the day's full move,
  including any gap from yesterday's close. ATR is its 14-day Wilder average, the
  typical daily move in dollars. It's used to compare volatility over time and to set
  stop-loss distances.
- **Volume moving average.** The 20-day average volume. It's "normal" activity, so a
  breakout on twice the usual volume can be told apart from one on a quiet day.

<!-- Phases 3–5 add signals, backtest metrics and ML evaluation terms. -->
