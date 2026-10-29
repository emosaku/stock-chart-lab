"""Rule-based signal detection on one ticker's prices + indicators.

A signal is an **event**, the day a condition *starts* (a line crosses another, RSI
leaves a zone), not every day it holds. "The 50-day is above the 200-day" is true for
months at a time; "the 50-day crossed above the 200-day today" happens once, and that
day is what a trading rule acts on.

No lookahead: a signal dated t uses only data up to t's close. Phase 4 then trades on
bar t+1, because a close-of-day event can't be traded at that same close.

Directions are the conventional readings. Whether they actually predicted anything is
exactly what Phase 4 tests, so nothing here claims they work.
"""

import pandas as pd

from stocklab.config import SignalSettings
from stocklab.signals.levels import active_levels, find_levels

SIGNAL_COLUMNS = [
    "ticker",
    "date",
    "signal",
    "direction",
    "price",
    "value",
    "volume_ratio",
    "detail",
]


def crossed_above(a: pd.Series | float, b: pd.Series | float) -> pd.Series:
    """True on the bar where ``a`` goes from <= ``b`` to > ``b``. Either side may be a
    fixed level (RSI 30). NaN on either bar (an indicator still warming up) gives
    False, so warm-up never fakes a cross."""
    index = a.index if isinstance(a, pd.Series) else b.index
    a = a if isinstance(a, pd.Series) else pd.Series(float(a), index=index)
    b = b if isinstance(b, pd.Series) else pd.Series(float(b), index=index)
    return ((a > b) & (a.shift() <= b.shift())).fillna(False).astype(bool)


def detect_signals(frame: pd.DataFrame, cfg: SignalSettings) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(signals, levels) for one ticker. ``frame`` = features.load_indicators output."""
    if frame.empty:
        return pd.DataFrame(columns=SIGNAL_COLUMNS), find_levels(frame, cfg.pivot_window)
    df = frame.sort_values("date").reset_index(drop=True)
    close = df["close"].astype(float)
    vol_ratio = df["volume"].astype(float) / df["volume_sma"]
    found: list[pd.DataFrame] = []

    def emit(mask: pd.Series, name: str, direction: str, value: pd.Series, detail) -> None:
        hit = df.index[mask]
        if len(hit):
            found.append(
                pd.DataFrame(
                    {
                        "ticker": df.loc[hit, "ticker"],
                        "date": df.loc[hit, "date"],
                        "signal": name,
                        "direction": direction,
                        "price": close[hit],
                        "value": value[hit].astype(float),
                        "volume_ratio": vol_ratio[hit],
                        "detail": [detail(i) for i in hit],
                    }
                )
            )

    # Golden / death cross: the 50-day average crossing the 200-day. The slow average
    # is the long-term trend; the fast one crossing it says the medium-term trend has
    # turned. Golden = up through (bullish), death = down through (bearish).
    f, s = cfg.cross_fast_sma, cfg.cross_slow_sma
    fast, slow = df[f"sma_{f}"], df[f"sma_{s}"]
    emit(
        crossed_above(fast, slow),
        "golden_cross",
        "bullish",
        fast,
        lambda i: f"SMA {f} {fast[i]:.2f} crossed above SMA {s} {slow[i]:.2f}",
    )
    emit(
        crossed_above(slow, fast),
        "death_cross",
        "bearish",
        fast,
        lambda i: f"SMA {f} {fast[i]:.2f} crossed below SMA {s} {slow[i]:.2f}",
    )

    # RSI: fires when RSI *leaves* the extreme zone, not when it enters. Entering
    # oversold during a crash can keep going lower for weeks ("catching a falling
    # knife"); climbing back above 30 is the first sign the selling has eased.
    rsi, lo, hi = df["rsi"], cfg.rsi_oversold, cfg.rsi_overbought
    emit(
        crossed_above(rsi, lo),
        "rsi_oversold_recovery",
        "bullish",
        rsi,
        lambda i: f"RSI rose back above {lo:g} to {rsi[i]:.1f}",
    )
    emit(
        crossed_above(hi, rsi),
        "rsi_overbought_reversal",
        "bearish",
        rsi,
        lambda i: f"RSI fell back below {hi:g} to {rsi[i]:.1f}",
    )

    # MACD crossing its signal line: short-term momentum turning up (bullish) or down.
    macd, sig = df["macd"], df["macd_signal"]
    emit(
        crossed_above(macd, sig),
        "macd_bullish_cross",
        "bullish",
        df["macd_hist"],
        lambda i: f"MACD {macd[i]:.2f} crossed above signal {sig[i]:.2f}",
    )
    emit(
        crossed_above(sig, macd),
        "macd_bearish_cross",
        "bearish",
        df["macd_hist"],
        lambda i: f"MACD {macd[i]:.2f} crossed below signal {sig[i]:.2f}",
    )

    # Bollinger breakouts: closing outside the bands = an unusually large move for the
    # recent volatility. Read here as momentum (up = bullish). The opposite,
    # mean-reversion reading ("stretched, will snap back") exists too, and Phase 4's
    # results will say which one the data supports.
    up, low = df["bb_upper"], df["bb_lower"]
    emit(
        crossed_above(close, up),
        "bb_breakout_up",
        "bullish",
        df["bb_pctb"],
        lambda i: f"closed {close[i]:.2f} above upper band {up[i]:.2f}",
    )
    emit(
        crossed_above(low, close),
        "bb_breakout_down",
        "bearish",
        df["bb_pctb"],
        lambda i: f"closed {close[i]:.2f} below lower band {low[i]:.2f}",
    )

    # Support / resistance breaks against the most recent confirmed swing level.
    levels = find_levels(df, cfg.pivot_window)
    act = active_levels(df, levels, cfg.max_level_age)
    res, sup = act["resistance"], act["support"]
    # Both closes are measured against today's active level: yesterday at or below it,
    # today above it. So the price has to move through the level, not just sit above a
    # level that was replaced overnight.
    brk = (close > res) & (close.shift() <= res)
    emit(
        brk.fillna(False),
        "resistance_breakout",
        "bullish",
        res,
        lambda i: f"closed {close[i]:.2f} above resistance {res[i]:.2f}",
    )
    bd = (close < sup) & (close.shift() >= sup)
    emit(
        bd.fillna(False),
        "support_breakdown",
        "bearish",
        sup,
        lambda i: f"closed {close[i]:.2f} below support {sup[i]:.2f}",
    )

    signals = (
        pd.concat(found, ignore_index=True).sort_values(["date", "signal"]).reset_index(drop=True)
        if found
        else pd.DataFrame(columns=SIGNAL_COLUMNS)
    )
    return signals, levels
