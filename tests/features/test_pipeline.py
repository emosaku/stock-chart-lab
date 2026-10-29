from datetime import UTC, date, datetime

from stocklab.features import load_indicators, run_indicators
from tests.conftest import make_history


def _seed(store, ticker="AAA", end=date(2023, 12, 29)):
    prices = make_history(ticker, date(2022, 1, 3), end).assign(
        source="t", ingested_at=datetime(2024, 1, 1)
    )
    store.upsert("prices_daily", prices)
    return prices


def test_writes_and_is_idempotent(store, settings):
    _seed(store)
    now = datetime(2024, 1, 2, tzinfo=UTC)
    first = run_indicators(settings, store, tickers=["AAA"], now=now)
    rows = store.read("indicators", "AAA")
    again = run_indicators(settings, store, tickers=["AAA"], now=now)
    assert first[0]["status"] == "ok" and first[0]["indicators"] == 16
    assert first[0]["rows_written"] == again[0]["rows_written"] == len(rows)
    assert store.read("indicators", "AAA").equals(rows)


def test_recompute_replaces_stale_rows(store, settings):
    _seed(store)
    run_indicators(settings, store, tickers=["AAA"])
    settings.indicators.sma_windows = [10]
    run_indicators(settings, store, tickers=["AAA"])
    names = set(store.read("indicators", "AAA")["indicator"])
    assert "sma_10" in names and "sma_200" not in names


def test_missing_prices_reported(store, settings):
    _seed(store)
    res = {r["ticker"]: r for r in run_indicators(settings, store)}
    assert res["AAA"]["status"] == "ok"
    assert res["BBB"]["status"] == "no_prices"


def test_load_indicators_is_one_row_per_day(store, settings):
    prices = _seed(store)
    run_indicators(settings, store, tickers=["AAA"])
    frame = load_indicators(store, "AAA")
    assert len(frame) == len(prices)
    assert {"close", "adj_close", "sma_200", "rsi", "bb_upper", "atr"} <= set(frame.columns)
    assert frame["sma_200"].isna().sum() == 199  # warm-up days have prices, no SMA 200
    sub = load_indicators(store, "AAA", start=date(2023, 6, 1), end=date(2023, 6, 30))
    assert sub["date"].min() >= date(2023, 6, 1) and sub["date"].max() <= date(2023, 6, 30)
