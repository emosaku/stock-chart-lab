"""Data-quality checks on daily bars.

Two kinds, with a simple severity policy:

- **Row checks** run on a freshly fetched batch *before* it is written. A row that
  fails one (``error``) is rejected and logged, because a null or impossible price
  would poison every indicator computed from it later.
- **Series checks** run on a ticker's stored history *after* the write. They find
  things a single row can't show, such as gaps and suspicious jumps. These are
  ``warn``: the data stays and the finding is logged for a human to look at, with one
  exception (an unadjusted split, which is an ``error`` because it's certainly wrong).

Every check returns rows of ISSUE_COLUMNS; nothing here raises on bad data.
"""

from datetime import date

import numpy as np
import pandas as pd

from stocklab.ingestion.calendar import sessions

ISSUE_COLUMNS = ["ticker", "check_name", "severity", "date", "detail"]
PRICE_FIELDS = ["open", "high", "low", "close", "adj_close"]


def _issues(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=ISSUE_COLUMNS)


# -- row checks ------------------------------------------------------------------------


def check_rows(prices: pd.DataFrame, calendar: str = "XNYS") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a fetched batch into (rows to keep, issues). Rejected rows are 'error'."""
    if prices.empty:
        return prices, _issues([])

    df = prices.reset_index(drop=True)
    reject = pd.Series(False, index=df.index)
    rows: list[tuple] = []

    def flag(mask: pd.Series, check: str, describe) -> None:
        nonlocal reject
        for i in df.index[mask]:
            rows.append((df.at[i, "ticker"], check, "error", df.at[i, "date"], describe(df.loc[i])))
        reject |= mask

    nulls = df[PRICE_FIELDS + ["volume"]].isna()
    flag(
        nulls.any(axis=1),
        "null_value",
        lambda r: "null in " + ", ".join(c for c in PRICE_FIELDS + ["volume"] if pd.isna(r[c])),
    )

    prices_num = df[PRICE_FIELDS].astype(float)
    flag(
        (prices_num <= 0).any(axis=1) & ~reject,
        "non_positive_price",
        lambda r: "price <= 0: " + ", ".join(f"{c}={r[c]}" for c in PRICE_FIELDS if r[c] <= 0),
    )

    # A bar's high must be the highest price of the day and its low the lowest. If not,
    # at least one of the four numbers is wrong. A tiny tolerance absorbs float noise.
    o, h, low, c = (prices_num[k] for k in ("open", "high", "low", "close"))
    tol = 1e-6 * h.abs()
    bad_ohlc = (h + tol < np.maximum(o, c)) | (low - tol > np.minimum(o, c)) | (low > h + tol)
    flag(
        bad_ohlc & ~reject,
        "ohlc_inconsistent",
        lambda r: f"O={r.open:.4f} H={r.high:.4f} L={r.low:.4f} C={r.close:.4f}",
    )

    vol = pd.to_numeric(df["volume"], errors="coerce")
    flag((vol < 0).fillna(False) & ~reject, "negative_volume", lambda r: f"volume={r.volume}")

    dupes = df.duplicated(subset=["ticker", "date"], keep="last")
    flag(dupes & ~reject, "duplicate_date", lambda r: "duplicate row; kept the last one")

    # A bar dated on a day the exchange was closed is either a timezone bug or bad data.
    if not df.empty:
        open_days = set(sessions(min(df["date"]), max(df["date"]), calendar))
        flag(
            ~df["date"].isin(open_days) & ~reject,
            "non_session_date",
            lambda r: f"{r.date} is not a {calendar} trading session",
        )

    # Zero volume on a full session is odd but not impossible for thin stocks, so warn.
    for i in df.index[(vol == 0).fillna(False) & ~reject]:
        rows.append((df.at[i, "ticker"], "zero_volume", "warn", df.at[i, "date"], "volume=0"))

    return df[~reject].reset_index(drop=True), _issues(rows)


# -- series checks ---------------------------------------------------------------------


def check_series(
    prices: pd.DataFrame,
    actions: pd.DataFrame,
    *,
    expected_last: date | None,
    max_daily_move: float = 0.25,
    calendar: str = "XNYS",
) -> pd.DataFrame:
    """Checks on one ticker's full stored history (sorted or not)."""
    if prices.empty:
        return _issues([])
    df = prices.sort_values("date").reset_index(drop=True)
    ticker = df["ticker"].iloc[0]
    rows: list[tuple] = []

    # Missing sessions: the exchange was open between our first and last bar, but we
    # have no bar for that day.
    have = set(df["date"])
    for d in sessions(df["date"].iloc[0], df["date"].iloc[-1], calendar):
        if d not in have:
            rows.append((ticker, "missing_session", "warn", d, "no bar on a trading day"))

    # Stale: the newest bar is older than the last completed session.
    last = df["date"].iloc[-1]
    if expected_last and last < expected_last:
        rows.append((ticker, "stale", "warn", last, f"latest bar {last}, expected {expected_last}"))

    # Big one-day moves. Adjusted prices already smooth splits out, so a big move is
    # either real news or bad data. Exception: if a split happened that day and the move
    # matches the split ratio, Yahoo failed to adjust the history -> certainly wrong.
    splits = {}
    if not actions.empty:
        s = actions[actions["action_type"] == "split"]
        splits = dict(zip(s["date"], s["value"], strict=True))
    ret = df["adj_close"].astype(float).pct_change()
    for i in df.index[ret.abs() > max_daily_move]:
        d, r = df.at[i, "date"], ret.iat[i]
        ratio = splits.get(d)
        if ratio and ratio > 0 and abs((1 + r) * ratio - 1) < 0.15:
            rows.append(
                (
                    ticker,
                    "split_not_adjusted",
                    "error",
                    d,
                    f"{r:+.1%} move matches a {ratio:g}:1 split; history not adjusted",
                )
            )
        else:
            rows.append((ticker, "large_move", "warn", d, f"adj_close moved {r:+.1%} in one day"))

    return _issues(rows)
