"""Support and resistance from swing highs and lows.

*Support* is a price level where buyers previously stepped in and the price turned up
(a swing low). *Resistance* is where sellers previously took over and it turned down (a
swing high). Traders watch for the price breaking through them: closing above resistance
suggests buyers have overwhelmed the sellers who stopped it before.

A swing high on bar i is a high that's the highest of the ``window`` bars on each side.
That definition needs bars *after* i, so the level only becomes known on bar
i + window, its ``confirmed_date``. Using it any earlier would be lookahead: on the day
of the swing high itself, nobody yet knows the price is about to turn down.
"""

import numpy as np
import pandas as pd


def find_levels(frame: pd.DataFrame, window: int) -> pd.DataFrame:
    """Confirmed swing-high (resistance) and swing-low (support) levels for one ticker."""
    cols = [
        "ticker",
        "pivot_date",
        "level_type",
        "price",
        "confirmed_date",
        "pivot_idx",
        "conf_idx",
    ]
    df = frame.sort_values("date").reset_index(drop=True)
    n = len(df)
    if n < 2 * window + 1:
        return pd.DataFrame(columns=cols)

    span = 2 * window + 1
    rows = []
    for col, kind, extreme in (("high", "resistance", "max"), ("low", "support", "min")):
        s = df[col].astype(float)
        # Centered window: deliberately looks ahead `window` bars to *define* the pivot.
        # The level is only released for use at conf_idx = i + window (below).
        ref = getattr(s.rolling(span, center=True), extreme)()
        is_pivot = (s == ref).to_numpy()
        # On a tie (same high twice in the window) keep the first, so a flat top is one level.
        for i in np.flatnonzero(is_pivot):
            lo = max(0, i - window)
            if (s.iloc[lo:i] == s.iloc[i]).any():
                continue
            conf = i + window
            rows.append(
                (
                    df.at[i, "ticker"],
                    df.at[i, "date"],
                    kind,
                    float(s.iloc[i]),
                    df.at[conf, "date"],
                    i,
                    conf,
                )
            )
    return (
        pd.DataFrame(rows, columns=cols)
        .sort_values(["conf_idx", "level_type"])
        .reset_index(drop=True)
    )


def active_levels(frame: pd.DataFrame, levels: pd.DataFrame, max_age: int) -> pd.DataFrame:
    """For each bar t, the most recent support and resistance confirmed *before* t and
    no older than ``max_age`` bars. Returns columns ``support`` and ``resistance``
    aligned to ``frame`` sorted by date."""
    n = len(frame)
    out = pd.DataFrame(index=range(n), columns=["support", "resistance"], dtype=float)
    for kind in ("support", "resistance"):
        lv = levels[levels["level_type"] == kind]
        price = np.full(n, np.nan)
        pivot = np.full(n, np.nan)
        # Several pivots confirming on the same bar only happens in degenerate data; last wins.
        conf = lv["conf_idx"].to_numpy(dtype=int)
        price[conf] = lv["price"].to_numpy(dtype=float)
        pivot[conf] = lv["pivot_idx"].to_numpy(dtype=float)
        # shift(1): a level confirmed at today's close is first usable tomorrow.
        price_s = pd.Series(price).ffill().shift(1)
        pivot_s = pd.Series(pivot).ffill().shift(1)
        age = pd.Series(np.arange(n, dtype=float)) - pivot_s
        out[kind] = price_s.where(age <= max_age)
    return out
