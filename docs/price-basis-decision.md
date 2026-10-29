# Price Basis Decision

Online version: https://claude.ai/artifact/6WeaiBGXiycni7kLqW64uN

Decided 2026-10-28: price levels and the day's range use the split-adjusted `close`
with its open/high/low. Returns use the split- and dividend-adjusted `adj_close`.

## The rule

If it's a dollar level or a daily range, use `close` and its open/high/low. If it's a
percentage change, use `adj_close`.

| Consumer | Phase | Column | Why |
|---|---|---|---|
| SMA / EMA 20/50/200 | 2 | `close` | Levels traders see on charts |
| Bollinger Bands | 2 | `close` | Bands are dollar levels around the SMA |
| RSI, MACD | 2 | `close` | Same basis as the other price-level indicators; the dividend effect is a tiny blip |
| ATR | 2 | `high`, `low`, `close` | Needs a consistent daily range; only the unadjusted bar has one |
| Volume moving average | 2 | `volume` | Not a price |
| Crosses, breakouts, support/resistance | 3 | `close` + indicators | Levels must match what traders saw |
| Trade returns, buy-and-hold, metrics | 4 | `adj_close` | Dividends are real money |
| Return features and targets | 5 | `adj_close` | The label should be the real outcome |
| Candlestick chart | 6 | `open`, `high`, `low`, `close` | Matches broker charts |

## close vs adj_close

The two columns differ only in dividends. When a stock pays one, its price drops by
about that amount on the ex-dividend date. `close` shows the drop; `adj_close` scales
all earlier prices down so the series tracks total return.

| | `close` | `adj_close` |
|---|---|---|
| Adjusted for splits | Yes | Yes |
| Adjusted for dividends | No | Yes |
| Matching open/high/low | Yes, same basis | No, Yahoo only adjusts the close |
| Changes after it's stored | Only on a split | After every dividend, all earlier values shift |

In our data (as of 2026-10-16) the gap is small:

| Ticker | Dividends | Each dividend, % of price | Largest gap, adj_close vs close |
|---|---|---|---|
| AMZN | none | — | 0% (identical) |
| GOOG | quarterly since 2024, $0.22 | ~0.06% | 0.94% |
| META | quarterly since 2024, $0.525 | ~0.08–0.09% | 0.95% |

## Options considered

| Option | Pros | Cons |
|---|---|---|
| `close` + its open/high/low | Matches broker charts and news; open, high, low and close share one basis (needed for ATR and candlesticks); stable between splits | Each ex-dividend day shows a false ~0.07% loss; returns leave out dividends, so buy-and-hold looks slightly worse than it was |
| `adj_close` | True total return; right for backtests and ML targets; no false ex-dividend drops | No matching open/high/low; old dollar levels up to ~1% off what traders saw; every dividend restates history, so indicators must be recomputed |
| Fully adjusted bar (O/H/L × adj_close/close) | Consistent bar and total return together | Open/high/low no longer Yahoo's own numbers; still restated on every dividend |

**Chosen:** a split by purpose. `close` and its bar for dollar levels and ranges,
`adj_close` for returns. Each use gets the column whose drawbacks don't matter for that
job.

## Consequences and when to revisit

- Phase 2 indicators are computed from `close` and its bar. Splits still restate that
  history, so indicators are recomputed in full for a ticker whenever its prices change.
  That takes seconds at this size.
- Phase 4 backtests compute trade and buy-and-hold returns from `adj_close`, even when
  the signal that triggered a trade came from `close`.
- Phase 5 return features and targets use `adj_close`.
- For GOOG, META and AMZN the choice moves indicator values by under 1%. Revisit if a
  high-dividend stock (3–4% a year, such as a utility) is added. A false ex-dividend
  drop of that size could then trip signals, and the fully adjusted bar may become the
  better basis.
