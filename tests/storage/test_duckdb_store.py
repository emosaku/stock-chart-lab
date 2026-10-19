from datetime import date, datetime

import pandas as pd
import pytest

from stocklab.storage.duckdb_store import DuckDBStorage
from tests.conftest import make_history


def _prices(ticker="AAA", start=date(2024, 1, 2), end=date(2024, 1, 31)):
    return make_history(ticker, start, end).assign(source="t", ingested_at=datetime(2024, 2, 1))


def test_init_schema_is_repeatable(store):
    store.init_schema()
    store.init_schema()
    assert store.read("prices_daily").empty


def test_upsert_is_idempotent(store):
    df = _prices()
    store.upsert("prices_daily", df)
    store.upsert("prices_daily", df)
    assert len(store.read("prices_daily")) == len(df)


def test_upsert_replaces_on_primary_key(store):
    df = _prices()
    store.upsert("prices_daily", df)
    changed = df.iloc[[0]].assign(close=1.0)
    store.upsert("prices_daily", changed)
    out = store.read("prices_daily")
    assert len(out) == len(df)
    assert out.loc[out["date"] == df["date"].iloc[0], "close"].item() == 1.0


def test_read_filters_and_returns_plain_dates(store):
    store.upsert("prices_daily", pd.concat([_prices("AAA"), _prices("BBB")]))
    out = store.read("prices_daily", "AAA", start=date(2024, 1, 10), end=date(2024, 1, 12))
    assert set(out["ticker"]) == {"AAA"}
    assert list(out["date"]) == [date(2024, 1, 10), date(2024, 1, 11), date(2024, 1, 12)]
    assert len(store.read("prices_daily", ["AAA", "BBB"])) == 2 * len(_prices())


def test_replace_ticker_leaves_other_tickers(store):
    store.upsert("prices_daily", pd.concat([_prices("AAA"), _prices("BBB")]))
    store.replace_ticker("prices_daily", "AAA", _prices("AAA", end=date(2024, 1, 5)))
    assert len(store.read("prices_daily", "AAA")) == 4  # Jan 2-5
    assert len(store.read("prices_daily", "BBB")) == len(_prices())


def test_replace_ticker_rolls_back_on_failure(store):
    store.upsert("prices_daily", _prices())
    with pytest.raises(ValueError):
        store.replace_ticker("prices_daily", "AAA", pd.DataFrame({"ticker": ["AAA"]}))
    assert len(store.read("prices_daily", "AAA")) == len(_prices())


def test_latest_dates(store):
    store.upsert("prices_daily", pd.concat([_prices("AAA"), _prices("BBB", end=date(2024, 1, 10))]))
    assert store.latest_dates() == {"AAA": date(2024, 1, 31), "BBB": date(2024, 1, 10)}


def test_unknown_table_and_append_only_upsert_rejected(store):
    with pytest.raises(ValueError):
        store.read("nope")
    with pytest.raises(ValueError):
        store.upsert("dq_issues", pd.DataFrame())


def test_file_backend_persists(tmp_path):
    path = tmp_path / "sub" / "lab.duckdb"
    with DuckDBStorage(path) as s:
        s.init_schema()
        s.upsert("prices_daily", _prices())
    with DuckDBStorage(path) as s:
        assert len(s.read("prices_daily")) == len(_prices())
