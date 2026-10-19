from datetime import date

import pandas as pd

from stocklab.ingestion.quality import check_rows, check_series
from tests.conftest import make_history

START, END = date(2024, 1, 2), date(2024, 2, 29)


def _checks(issues):
    return set(issues["check_name"])


def test_clean_data_has_no_issues():
    df = make_history("AAA", START, END)
    kept, issues = check_rows(df)
    assert len(kept) == len(df) and issues.empty
    assert check_series(df, pd.DataFrame(), expected_last=END).empty


def test_bad_rows_rejected_with_reasons():
    df = make_history("AAA", START, END)
    df.loc[1, "close"] = None  # null
    df.loc[2, "low"] = -1.0  # impossible price
    df.loc[3, "high"] = df.loc[3, "low"] * 0.9  # high below low
    df.loc[4, "volume"] = -5
    df = pd.concat([df, df.iloc[[10]]], ignore_index=True)  # duplicate date
    df.loc[5, "volume"] = 0  # suspicious but kept

    kept, issues = check_rows(df)
    errors = issues[issues["severity"] == "error"]
    assert _checks(errors) == {
        "null_value",
        "non_positive_price",
        "ohlc_inconsistent",
        "negative_volume",
        "duplicate_date",
    }
    assert len(kept) == len(df) - 5
    assert not kept.duplicated(["ticker", "date"]).any()
    assert _checks(issues[issues["severity"] == "warn"]) == {"zero_volume"}
    assert df.loc[5, "date"] in set(kept["date"])


def test_bar_on_a_holiday_rejected():
    df = make_history("AAA", START, END)
    holiday = df.iloc[[0]].assign(date=date(2024, 1, 15))  # MLK day
    kept, issues = check_rows(pd.concat([df, holiday], ignore_index=True))
    assert _checks(issues) == {"non_session_date"}
    assert date(2024, 1, 15) not in set(kept["date"])


def test_missing_session_and_stale():
    df = make_history("AAA", START, END)
    df = df[df["date"] != date(2024, 1, 17)]
    issues = check_series(df, pd.DataFrame(), expected_last=date(2024, 3, 4))
    assert set(zip(issues["check_name"], issues["date"], strict=True)) == {
        ("missing_session", date(2024, 1, 17)),
        ("stale", END),
    }


def test_large_move_is_a_warning():
    df = make_history("AAA", START, END)
    df.loc[20:, "adj_close"] *= 0.7  # a real-looking 30% drop
    issues = check_series(df, pd.DataFrame(), expected_last=END)
    assert list(issues["check_name"]) == ["large_move"]
    assert issues["severity"].item() == "warn"
    assert issues["date"].item() == df.loc[20, "date"]


def test_unadjusted_split_is_an_error():
    df = make_history("AAA", START, END)
    split_day = df.loc[20, "date"]
    df.loc[20:, "adj_close"] /= 20  # source forgot to back-adjust a 20:1 split
    actions = pd.DataFrame(
        [{"ticker": "AAA", "date": split_day, "action_type": "split", "value": 20.0}]
    )
    issues = check_series(df, actions, expected_last=END)
    assert list(issues["check_name"]) == ["split_not_adjusted"]
    assert issues["severity"].item() == "error"
