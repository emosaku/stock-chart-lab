"""Price sources. The pipeline depends on the ``PriceSource`` protocol only.

yfinance is the only source today. It is an unofficial Yahoo Finance scraper: free and
fine for research, but with no uptime or accuracy guarantee. A paid feed would be a
second class with the same ``fetch`` signature; nothing else changes.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

import pandas as pd

PRICE_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "adj_close", "volume"]
ACTION_COLUMNS = ["ticker", "date", "action_type", "value"]


@dataclass
class FetchResult:
    prices: pd.DataFrame  # PRICE_COLUMNS, one row per session
    actions: pd.DataFrame  # ACTION_COLUMNS, one row per split/dividend


class PriceSource(Protocol):
    name: str

    def fetch(self, ticker: str, start: date, end: date) -> FetchResult:
        """Daily bars and corporate actions for ``ticker`` in [start, end], inclusive."""


class YahooSource:
    name = "yfinance"

    def fetch(self, ticker: str, start: date, end: date) -> FetchResult:
        import yfinance as yf

        # auto_adjust=False keeps both Close (split-adjusted) and Adj Close (split- and
        # dividend-adjusted). yfinance's `end` is exclusive, hence +1 day.
        raw = yf.Ticker(ticker).history(
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
            raise_errors=False,
        )
        return normalise_yahoo(raw, ticker)


def normalise_yahoo(raw: pd.DataFrame, ticker: str) -> FetchResult:
    """Turn a yfinance ``history()`` frame into our column names and types."""
    if raw is None or raw.empty:
        return FetchResult(_empty(PRICE_COLUMNS), _empty(ACTION_COLUMNS))

    df = raw.copy()
    # The index is midnight in the exchange's timezone (America/New_York); the session
    # date is that local calendar date. Dropping tz before taking .date avoids an
    # off-by-one from converting to UTC first.
    idx = df.index.tz_localize(None) if df.index.tz is not None else df.index
    df.index = idx.normalize().date
    df.index.name = "date"

    prices = (
        df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Adj Close": "adj_close",
                "Volume": "volume",
            }
        )
        .reset_index()
        .assign(ticker=ticker)
    )
    for col in PRICE_COLUMNS:
        if col not in prices:
            prices[col] = pd.NA
    prices = prices[PRICE_COLUMNS]
    prices["volume"] = pd.to_numeric(prices["volume"], errors="coerce").astype("Int64")

    actions = []
    for col, kind in (("Stock Splits", "split"), ("Dividends", "dividend")):
        if col in df:
            hits = df.loc[df[col].fillna(0) != 0, col]
            actions += [(ticker, d, kind, float(v)) for d, v in hits.items()]
    return FetchResult(prices, pd.DataFrame(actions, columns=ACTION_COLUMNS))


def _empty(columns: list[str]) -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})
