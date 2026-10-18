"""Settings file parses, validates, and normalises tickers."""

import pytest
from pydantic import ValidationError

from stocklab.config import Settings, load_settings


def test_project_settings_load():
    settings = load_settings()
    assert {"GOOG", "META", "AMZN"} <= set(settings.data.tickers)


def test_tickers_are_normalised():
    s = Settings.model_validate(
        {"data": {"tickers": [" goog", "Meta"], "start_date": "2015-01-01"}}
    )
    assert s.data.tickers == ["GOOG", "META"]


@pytest.mark.parametrize("tickers", [[], ["GOOG", "goog"]])
def test_bad_ticker_lists_rejected(tickers):
    with pytest.raises(ValidationError):
        Settings.model_validate({"data": {"tickers": tickers, "start_date": "2015-01-01"}})
