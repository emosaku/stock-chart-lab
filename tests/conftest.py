"""Shared fixtures. Nothing here touches the network: prices come from FakeSource, a
deterministic stand-in for yfinance that tests can tamper with (restate history, add a
partial bar, inject bad rows)."""

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from stocklab.config import Settings
from stocklab.ingestion.calendar import sessions
from stocklab.ingestion.source import ACTION_COLUMNS, PRICE_COLUMNS, FetchResult
from stocklab.storage.duckdb_store import DuckDBStorage


def make_history(ticker: str, start: date, end: date, seed: int = 0) -> pd.DataFrame:
    """A plausible random-walk price series on real NYSE sessions."""
    days = sessions(start, end)
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(days))))
    open_ = close * (1 + rng.normal(0, 0.003, len(days)))
    high = np.maximum(open_, close) * 1.005
    low = np.minimum(open_, close) * 0.995
    return pd.DataFrame(
        {
            "ticker": ticker,
            "date": days,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "adj_close": close * 0.99,
            "volume": rng.integers(1_000_000, 5_000_000, len(days)),
        }
    )[PRICE_COLUMNS]


class FakeSource:
    name = "fake"

    def __init__(self, prices: dict[str, pd.DataFrame], actions: dict[str, pd.DataFrame] = None):
        self.prices = prices
        self.actions = actions or {}
        self.calls: list[tuple[str, date, date]] = []

    def fetch(self, ticker, start, end):
        self.calls.append((ticker, start, end))
        if ticker not in self.prices:
            return FetchResult(
                pd.DataFrame(columns=PRICE_COLUMNS), pd.DataFrame(columns=ACTION_COLUMNS)
            )
        p = self.prices[ticker]
        a = self.actions.get(ticker, pd.DataFrame(columns=ACTION_COLUMNS))
        in_range = (p["date"] >= start) & (p["date"] <= end)
        a_range = (a["date"] >= start) & (a["date"] <= end) if not a.empty else []
        return FetchResult(p[in_range].copy(), a[a_range].copy() if not a.empty else a.copy())


@pytest.fixture
def store():
    s = DuckDBStorage(":memory:")
    s.init_schema()
    yield s
    s.close()


@pytest.fixture
def settings():
    return Settings.model_validate(
        {"data": {"tickers": ["AAA", "BBB"], "start_date": "2024-01-02", "overlap_days": 3}}
    )


def at_close(d: date) -> datetime:
    """A moment safely after that day's 4pm ET close (22:00 UTC)."""
    return datetime(d.year, d.month, d.day, 22, 0, tzinfo=UTC)
