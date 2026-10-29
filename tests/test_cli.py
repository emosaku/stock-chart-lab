"""CLI wiring: ingest and status run end to end against a temp DB and FakeSource."""

from datetime import date

import pytest

from stocklab import cli, config
from stocklab.ingestion import source
from tests.conftest import FakeSource, make_history


@pytest.fixture
def env(tmp_path, monkeypatch, settings):
    monkeypatch.setattr(config, "STOCKLAB_DB_PATH", str(tmp_path / "lab.duckdb"))
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    fake = FakeSource({"AAA": make_history("AAA", date(2024, 1, 2), date(2024, 1, 31))})
    monkeypatch.setattr(source, "YahooSource", lambda: fake)
    return fake


def test_ingest_then_status(env, capsys):
    # BBB is configured but the fake has no data for it -> that ticker fails -> exit 1
    assert cli.main(["ingest"]) == 1
    out = capsys.readouterr().out
    assert "AAA" in out and "backfill" in out and "failed" in out

    assert cli.main(["status"]) == 0
    out = capsys.readouterr().out
    assert "AAA" in out and "2024-01-31" in out


def test_ingest_subset_succeeds(env, capsys):
    assert cli.main(["ingest", "--tickers", "aaa"]) == 0


def test_ingest_rejects_unconfigured_ticker(env, capsys):
    assert cli.main(["ingest", "--tickers", "ZZZ"]) == 2


def test_indicators_after_ingest(env, capsys):
    assert cli.main(["ingest", "--tickers", "AAA"]) == 0
    assert cli.main(["indicators", "--tickers", "AAA"]) == 0
    out = capsys.readouterr().out
    assert "AAA" in out and "ok" in out
    # BBB has no prices -> reported, non-zero exit
    assert cli.main(["indicators"]) == 1


def test_signals_after_indicators(env, capsys, monkeypatch):
    # make the fake source long enough for SMA 200 so crosses can exist
    from tests.conftest import make_history

    env.prices["AAA"] = make_history("AAA", date(2024, 1, 2), date(2025, 6, 30), seed=4)
    assert cli.main(["ingest", "--tickers", "AAA"]) == 0
    assert cli.main(["indicators", "--tickers", "AAA"]) == 0
    capsys.readouterr()
    assert cli.main(["signals", "--tickers", "AAA", "--recent", "3"]) == 0
    out = capsys.readouterr().out
    assert "Signal counts" in out and "3 most recent" in out


def test_status_on_empty_db(env, capsys):
    assert cli.main(["status"]) == 0
    assert "no prices stored yet" in capsys.readouterr().out
