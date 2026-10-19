"""Which days the exchange was open.

A *trading session* is one day the exchange is open. NYSE closes on weekends, nine-ish
holidays a year (including Good Friday, which isn't a federal holiday), and the
occasional one-off day (Hurricane Sandy in Oct 2012, presidential funerals). So "every
weekday" is the wrong yardstick for gaps; the exchange's own calendar is the right one.
"""

from datetime import date, datetime, timedelta
from functools import lru_cache

import exchange_calendars as xc
import pandas as pd

# exchange_calendars only builds ~20 years back by default; ask for more explicitly.
_CALENDAR_START = "1990-01-01"


@lru_cache(maxsize=4)
def get_calendar(name: str = "XNYS") -> xc.ExchangeCalendar:
    return xc.get_calendar(name, start=_CALENDAR_START)


def sessions(start: date, end: date, calendar: str = "XNYS") -> list[date]:
    """Trading sessions in [start, end], inclusive."""
    if end < start:
        return []
    cal = get_calendar(calendar)
    end = min(end, cal.last_session.date())
    return [ts.date() for ts in cal.sessions_in_range(start, end)]


def last_completed_session(now: datetime, calendar: str = "XNYS") -> date:
    """The most recent session whose closing bell has rung as of ``now`` (tz-aware).

    During market hours Yahoo returns a partial bar for today, with a "close" that is
    just the latest trade. Storing it would put a half-day in the table, so ingestion
    stops at the last session that has actually finished.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    cal = get_calendar(calendar)
    now_ts = pd.Timestamp(now).tz_convert("UTC")
    recent = cal.sessions_in_range(now_ts.date() - timedelta(days=14), now_ts.date())
    for session in reversed(recent):
        if cal.session_close(session) <= now_ts:
            return session.date()
    raise RuntimeError(f"no completed session in the 14 days before {now}")


def previous_session(day: date, n: int = 1, calendar: str = "XNYS") -> date:
    """The session ``n`` sessions before ``day`` (``day`` itself need not be a session)."""
    window = sessions(day - timedelta(days=n * 2 + 14), day - timedelta(days=1), calendar)
    if len(window) < n:
        raise ValueError(f"fewer than {n} sessions before {day}")
    return window[-n]
