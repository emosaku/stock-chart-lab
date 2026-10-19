"""End-to-end ingest behaviour against FakeSource and in-memory DuckDB."""

from datetime import UTC, date, datetime

import pandas as pd

from stocklab.ingestion.pipeline import ingest
from tests.conftest import FakeSource, at_close, make_history

D1 = date(2024, 3, 1)  # first run "today"
D2 = date(2024, 3, 8)  # a week later


def _source(end=date(2024, 3, 29)):
    # The source knows the "future" too; ingest must only take what's complete by `now`.
    return FakeSource(
        {
            "AAA": make_history("AAA", date(2024, 1, 2), end, seed=1),
            "BBB": make_history("BBB", date(2024, 1, 2), end, seed=2),
        }
    )


def _by_ticker(runs):
    return {r.ticker: r for r in runs}


def test_backfill_then_rerun_is_a_noop(store, settings):
    src = _source()
    runs = _by_ticker(ingest(settings, store, src, now=at_close(D1)))
    assert {r.mode for r in runs.values()} == {"backfill"}
    assert {r.status for r in runs.values()} == {"ok"}
    assert store.latest_dates() == {"AAA": D1, "BBB": D1}
    n = len(store.read("prices_daily"))

    src.calls.clear()
    again = ingest(settings, store, src, now=at_close(D1))
    assert {r.mode for r in again} == {"up_to_date"}
    assert src.calls == []  # nothing fetched
    assert len(store.read("prices_daily")) == n


def test_incremental_fetches_only_overlap_plus_new_days(store, settings):
    src = _source()
    ingest(settings, store, src, now=at_close(D1))
    src.calls.clear()

    runs = _by_ticker(ingest(settings, store, src, now=at_close(D2)))
    assert runs["AAA"].mode == "incremental"
    # overlap_days=3: re-fetch Feb 28, Feb 29, Mar 1, then the new week
    assert src.calls[0] == ("AAA", date(2024, 2, 28), D2)
    assert store.latest_dates()["AAA"] == D2
    expected = make_history("AAA", date(2024, 1, 2), D2, seed=1)
    stored = store.read("prices_daily", "AAA")
    assert list(stored["date"]) == list(expected["date"])
    pd.testing.assert_series_equal(stored["close"], expected["close"], check_names=False)


def test_partial_bar_for_today_is_not_stored(store, settings):
    midday = datetime(2024, 3, 1, 16, 0, tzinfo=UTC)  # 11am ET, market open
    ingest(settings, store, _source(), now=midday)
    assert store.latest_dates()["AAA"] == date(2024, 2, 29)


def test_restatement_triggers_full_refresh(store, settings):
    src = _source()
    ingest(settings, store, src, now=at_close(D1))

    # A dividend goes ex on Mar 5: the source back-adjusts every earlier adj_close.
    p = src.prices["AAA"]
    p.loc[p["date"] < date(2024, 3, 5), "adj_close"] *= 0.995
    src.actions["AAA"] = pd.DataFrame(
        [{"ticker": "AAA", "date": date(2024, 3, 5), "action_type": "dividend", "value": 0.5}]
    )

    runs = _by_ticker(ingest(settings, store, src, now=at_close(D2)))
    assert runs["AAA"].mode == "refresh"
    assert runs["BBB"].mode == "incremental"
    stored = store.read("prices_daily", "AAA")
    truth = p[p["date"] <= D2].reset_index(drop=True)
    pd.testing.assert_series_equal(stored["adj_close"], truth["adj_close"], check_names=False)
    assert store.read("corporate_actions", "AAA")["action_type"].tolist() == ["dividend"]


def test_late_correction_to_last_bar_is_picked_up_without_refresh(store, settings):
    src = _source()
    ingest(settings, store, src, now=at_close(D1))
    p = src.prices["AAA"]
    # The Mar 1 close firmed up after we read it (small enough to stay inside the high).
    p.loc[p["date"] == D1, "close"] *= 1.002

    runs = _by_ticker(ingest(settings, store, src, now=at_close(D2)))
    assert runs["AAA"].mode == "incremental"
    stored = store.read("prices_daily", "AAA", start=D1, end=D1)
    assert stored["close"].item() == p.loc[p["date"] == D1, "close"].item()


def test_bad_ticker_fails_alone(store, settings):
    settings.data.tickers.append("NOPE")
    runs = _by_ticker(ingest(settings, store, _source(), now=at_close(D1)))
    assert runs["NOPE"].status == "failed"
    assert "no data" in runs["NOPE"].message
    assert runs["AAA"].status == runs["BBB"].status == "ok"
    logged = store.read("ingest_runs").set_index("ticker")["status"].to_dict()
    assert logged == {"AAA": "ok", "BBB": "ok", "NOPE": "failed"}


def test_rejected_rows_and_findings_are_logged(store, settings):
    src = _source()
    p = src.prices["AAA"]
    p.loc[p["date"] == date(2024, 2, 1), "close"] = None
    runs = _by_ticker(ingest(settings, store, src, now=at_close(D1)))

    run = runs["AAA"]
    assert run.status == "error"
    assert run.rows_rejected == 1
    assert date(2024, 2, 1) not in set(store.read("prices_daily", "AAA")["date"])
    issues = store.read("dq_issues", "AAA")
    # The rejected row shows up twice: as the error, and as the gap it leaves.
    assert set(zip(issues["check_name"], issues["severity"], strict=True)) == {
        ("null_value", "error"),
        ("missing_session", "warn"),
    }
    assert set(issues["run_id"]) == {run.run_id}


def test_end_date_caps_the_fetch(store, settings):
    settings.data.end_date = date(2024, 2, 15)
    ingest(settings, store, _source(), now=at_close(D1))
    assert store.latest_dates() == {"AAA": date(2024, 2, 15), "BBB": date(2024, 2, 15)}


def test_full_refresh_replaces_history(store, settings):
    src = _source()
    ingest(settings, store, src, now=at_close(D1))
    settings.data.start_date = date(2024, 2, 1)
    runs = ingest(settings, store, src, now=at_close(D1), full_refresh=True)
    assert {r.mode for r in runs} == {"backfill"}
    assert store.read("prices_daily", "AAA")["date"].min() == date(2024, 2, 1)
