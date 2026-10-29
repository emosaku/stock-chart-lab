from datetime import date, datetime

from stocklab.features import run_indicators
from stocklab.signals import run_signals
from tests.conftest import make_history


def _seed(store, settings, ticker="AAA"):
    prices = make_history(ticker, date(2021, 1, 4), date(2023, 12, 29), seed=5).assign(
        source="t", ingested_at=datetime(2024, 1, 1)
    )
    store.upsert("prices_daily", prices)
    run_indicators(settings, store, tickers=[ticker])


def test_writes_signals_and_levels_idempotently(store, settings):
    _seed(store, settings)
    first = run_signals(settings, store, tickers=["AAA"])
    sig = store.read("signals", "AAA")
    lv = store.read("price_levels", "AAA")
    again = run_signals(settings, store, tickers=["AAA"])
    assert first[0]["status"] == "ok" and first[0]["signals"] == len(sig) > 0
    assert again[0]["signals"] == len(store.read("signals", "AAA"))
    assert len(store.read("price_levels", "AAA")) == len(lv) > 0
    assert set(sig["direction"]) <= {"bullish", "bearish"}


def test_missing_indicators_reported(store, settings):
    _seed(store, settings)
    res = {r["ticker"]: r for r in run_signals(settings, store)}
    assert res["AAA"]["status"] == "ok"
    assert res["BBB"]["status"] == "no_indicators"
