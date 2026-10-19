"""YahooSource normalisation, with yfinance mocked out."""

from datetime import date

import pandas as pd

from stocklab.ingestion import source
from stocklab.ingestion.source import YahooSource, normalise_yahoo


def _yahoo_frame():
    # Shape of yf.Ticker(...).history(auto_adjust=False, actions=True): tz-aware
    # midnight-in-New-York index, capitalised columns, actions inline.
    idx = pd.DatetimeIndex(["2022-07-15", "2022-07-18", "2022-07-19"], name="Date").tz_localize(
        "America/New_York"
    )
    return pd.DataFrame(
        {
            "Open": [112.96, 113.44, 111.73],
            "High": [114.00, 114.80, 114.81],
            "Low": [111.82, 109.30, 111.13],
            "Close": [113.59, 109.89, 114.68],
            "Adj Close": [112.90, 109.22, 113.98],
            "Volume": [42_000_000, 31_000_000, 30_000_000],
            "Dividends": [0.0, 0.0, 0.2],
            "Stock Splits": [0.0, 20.0, 0.0],
        },
        index=idx,
    )


def test_normalise_columns_dates_and_actions():
    res = normalise_yahoo(_yahoo_frame(), "GOOG")
    assert list(res.prices.columns) == source.PRICE_COLUMNS
    # Local exchange date, not shifted by the UTC offset
    assert list(res.prices["date"]) == [date(2022, 7, 15), date(2022, 7, 18), date(2022, 7, 19)]
    assert res.prices["adj_close"].iloc[0] == 112.90
    assert res.actions.to_dict("records") == [
        {"ticker": "GOOG", "date": date(2022, 7, 18), "action_type": "split", "value": 20.0},
        {"ticker": "GOOG", "date": date(2022, 7, 19), "action_type": "dividend", "value": 0.2},
    ]


def test_normalise_empty():
    res = normalise_yahoo(pd.DataFrame(), "NOPE")
    assert res.prices.empty and res.actions.empty
    assert list(res.prices.columns) == source.PRICE_COLUMNS


def test_fetch_passes_inclusive_end_and_unadjusted(monkeypatch):
    seen = {}

    class FakeTicker:
        def __init__(self, symbol):
            seen["symbol"] = symbol

        def history(self, **kw):
            seen.update(kw)
            return _yahoo_frame()

    import yfinance

    monkeypatch.setattr(yfinance, "Ticker", FakeTicker)
    res = YahooSource().fetch("GOOG", date(2022, 7, 15), date(2022, 7, 19))
    assert seen["symbol"] == "GOOG"
    assert seen["end"] == "2022-07-20"  # yfinance end is exclusive
    assert seen["auto_adjust"] is False
    assert len(res.prices) == 3
