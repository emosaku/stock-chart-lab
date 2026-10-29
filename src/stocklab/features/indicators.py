"""Technical indicators computed from one ticker's daily bars.

Price basis (docs/price-basis-decision.md): every indicator here describes price
*levels* or the day's *range*, so it uses Yahoo's split-adjusted ``close``/``high``/
``low``, which match the charts traders look at. Return calculations elsewhere use
``adj_close``.

No lookahead: every indicator is a trailing calculation, so its value on day t uses
only bars up to and including t. The first few rows of each have no value while
the window fills (the *warm-up*: 199 bars for SMA 200). Those rows are dropped rather
than stored as nulls.

pandas-ta is called with ``talib=False`` so results never depend on whether the
optional TA-Lib C library happens to be installed.
"""

import pandas as pd
import pandas_ta as ta

from stocklab.config import IndicatorSettings


def compute_indicators(prices: pd.DataFrame, cfg: IndicatorSettings) -> pd.DataFrame:
    """Long-form indicators (ticker, date, indicator, value, params) for one ticker."""
    if prices.empty:
        return pd.DataFrame(columns=["ticker", "date", "indicator", "value", "params"])
    if prices["ticker"].nunique() != 1:
        raise ValueError("compute_indicators expects one ticker at a time")

    df = prices.sort_values("date").reset_index(drop=True)
    close = df["close"].astype(float)
    high, low = df["high"].astype(float), df["low"].astype(float)
    volume = df["volume"].astype(float)
    out: dict[str, tuple[pd.Series, str]] = {}

    # Moving averages smooth out day-to-day noise to show the trend. SMA = plain
    # average of the last n closes. EMA = weighted average that leans toward recent
    # days, so it turns sooner. 20/50/200 days are roughly a month, a quarter and a
    # trading year; price above its 200-day average is the classic "uptrend" test.
    for n in cfg.sma_windows:
        out[f"sma_{n}"] = (ta.sma(close, length=n, talib=False), f"length={n}")
    for n in cfg.ema_windows:
        out[f"ema_{n}"] = (ta.ema(close, length=n, talib=False), f"length={n}")

    # RSI (Relative Strength Index), 0-100: compares the size of recent up days with
    # recent down days using Wilder's smoothing. Above 70 is conventionally
    # "overbought" (rose fast, may pause), below 30 "oversold".
    # It needs n day-to-day changes, i.e. n+1 bars; pandas-ta emits values from the
    # second bar (GOOG's first 2010 days were all down -> RSI 0), so the warm-up is
    # enforced here.
    n = cfg.rsi_length
    out["rsi"] = (_warm_up(ta.rsi(close, length=n, talib=False), n), f"length={n}")

    # MACD: fast EMA minus slow EMA, i.e. how far short-term momentum is running ahead
    # of the longer trend. The signal line is an EMA of MACD itself; the histogram is
    # MACD minus signal. MACD crossing above its signal is read as momentum turning up.
    m = cfg.macd
    macd = _frame(ta.macd(close, fast=m.fast, slow=m.slow, signal=m.signal, talib=False), 3)
    p = f"fast={m.fast},slow={m.slow},signal={m.signal}"
    out["macd"] = (macd[0], p)
    out["macd_hist"] = (macd[1], p)
    out["macd_signal"] = (macd[2], p)

    # Bollinger Bands: a moving average with bands k standard deviations above and
    # below. Wide bands = volatile, narrow = quiet. %B places the close inside the
    # bands: 0 = on the lower band, 1 = on the upper, above 1 = broke out above.
    # ddof=0 (population std) is Bollinger's definition and TA-Lib's; pandas-ta's own
    # default is ddof=1 even though its docstring says 0, so it's passed explicitly.
    b = cfg.bollinger
    bb = _frame(
        ta.bbands(close, length=b.length, lower_std=b.std, upper_std=b.std, ddof=0, talib=False),
        5,
    )
    p = f"length={b.length},std={b.std:g}"
    out["bb_lower"] = (bb[0], p)
    out["bb_middle"] = (bb[1], p)
    out["bb_upper"] = (bb[2], p)
    out["bb_pctb"] = (bb[4], p)

    # ATR (Average True Range): the typical size of a day's move in dollars, including
    # overnight gaps. Used to size stops and to compare volatility over time.
    n = cfg.atr_length
    # True range needs the previous close, so the first full window ends on bar n
    # (TA-Lib's convention); pandas-ta starts a bar early using a partial first range.
    out["atr"] = (_warm_up(ta.atr(high, low, close, length=n, talib=False), n), f"length={n}")

    # Volume moving average: what "normal" trading activity looks like, so a breakout
    # on 2x average volume can be told apart from one on a quiet day.
    n = cfg.volume_ma_window
    out["volume_sma"] = (ta.sma(volume, length=n, talib=False), f"length={n}")

    frames = [
        pd.DataFrame(
            {"ticker": df["ticker"], "date": df["date"], "indicator": name, "value": s, "params": p}
        )
        for name, (s, p) in out.items()
        if s is not None
    ]
    if not frames:
        return compute_indicators(prices.iloc[:0], cfg)
    long = pd.concat(frames, ignore_index=True)
    return long.dropna(subset=["value"]).reset_index(drop=True)


def _warm_up(series: pd.Series | None, first: int) -> pd.Series | None:
    """Blank out values before bar index ``first`` (0-based), the first bar with a full
    window behind it."""
    if series is None:
        return None
    series = series.copy()
    series.iloc[:first] = float("nan")
    return series


def _frame(result: pd.DataFrame | None, width: int) -> list[pd.Series | None]:
    """Columns of a multi-output pandas-ta result. pandas-ta returns None, not an empty
    frame, when there are fewer bars than the window (a newly listed stock)."""
    if result is None:
        return [None] * width
    return [result.iloc[:, i] for i in range(width)]


def to_wide(long: pd.DataFrame) -> pd.DataFrame:
    """One row per (ticker, date), one column per indicator: the shape signals and
    the dashboard want."""
    if long.empty:
        return pd.DataFrame(columns=["ticker", "date"])
    wide = long.pivot_table(
        index=["ticker", "date"], columns="indicator", values="value", aggfunc="first"
    )
    wide.columns.name = None
    return wide.reset_index()
