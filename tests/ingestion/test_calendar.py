from datetime import UTC, date, datetime

import pytest

from stocklab.ingestion.calendar import last_completed_session, previous_session, sessions


def test_holidays_and_one_off_closures_excluded():
    # Good Friday 2024 (not a federal holiday, but NYSE closes)
    assert date(2024, 3, 29) not in sessions(date(2024, 3, 25), date(2024, 4, 1))
    # Hurricane Sandy closed NYSE on 2012-10-29 and 10-30
    assert sessions(date(2012, 10, 26), date(2012, 10, 31)) == [
        date(2012, 10, 26),
        date(2012, 10, 31),
    ]
    # National day of mourning for President Carter, 2025-01-09
    assert date(2025, 1, 9) not in sessions(date(2025, 1, 6), date(2025, 1, 10))


def test_last_completed_session_waits_for_the_close():
    friday = date(2024, 3, 15)  # 4pm ET = 20:00 UTC (daylight time)
    assert last_completed_session(datetime(2024, 3, 15, 15, 0, tzinfo=UTC)) == date(2024, 3, 14)
    assert last_completed_session(datetime(2024, 3, 15, 20, 1, tzinfo=UTC)) == friday
    # Over the weekend the answer stays Friday
    assert last_completed_session(datetime(2024, 3, 17, 12, 0, tzinfo=UTC)) == friday


def test_last_completed_session_needs_tz():
    with pytest.raises(ValueError):
        last_completed_session(datetime(2024, 3, 15, 22, 0))


def test_previous_session_skips_weekends():
    assert previous_session(date(2024, 3, 18)) == date(2024, 3, 15)
    assert previous_session(date(2024, 3, 18), n=3) == date(2024, 3, 13)
