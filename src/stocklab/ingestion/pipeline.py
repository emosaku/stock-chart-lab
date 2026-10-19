"""``stocklab ingest``: bring prices_daily up to date for every configured ticker.

Per ticker, one of four modes:

- **backfill**: nothing stored yet (or ``--full-refresh``). Fetch everything from
  ``start_date`` and replace the ticker's rows.
- **incremental**: fetch from a few sessions *before* the latest stored bar up to the
  last completed session, and upsert. Re-fetching that overlap picks up late
  corrections to recent bars.
- **refresh**: an incremental run noticed that the overlap no longer matches what
  is stored. Yahoo back-adjusts the whole history when a split or dividend happens
  (a 20:1 split divides every earlier price by 20, and each dividend nudges every
  earlier adj_close down a little). Appending new rows onto old ones would join two
  different adjustment bases, so the ticker is re-fetched in full instead.
- **up_to_date**: already have the last completed session; nothing to fetch.

Idempotent: running it twice in a row changes nothing the second time. Failures are
isolated per ticker, so one bad symbol doesn't stop the others.
"""

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime

import pandas as pd

from stocklab.config import DataSettings, Settings
from stocklab.ingestion.calendar import last_completed_session, previous_session
from stocklab.ingestion.quality import ISSUE_COLUMNS, check_rows, check_series
from stocklab.ingestion.source import FetchResult, PriceSource
from stocklab.storage import Storage

log = logging.getLogger(__name__)


@dataclass
class TickerRun:
    run_id: str
    ticker: str
    started_at: datetime
    finished_at: datetime | None = None
    mode: str = ""
    fetch_start: date | None = None
    fetch_end: date | None = None
    rows_fetched: int = 0
    rows_written: int = 0
    rows_rejected: int = 0
    dq_errors: int = 0
    dq_warnings: int = 0
    status: str = "ok"
    message: str = ""
    issues: pd.DataFrame = field(default_factory=lambda: pd.DataFrame(columns=ISSUE_COLUMNS))

    def record(self) -> dict:
        d = asdict(self)
        d.pop("issues")
        return d


def ingest(
    settings: Settings,
    store: Storage,
    source: PriceSource,
    *,
    tickers: list[str] | None = None,
    full_refresh: bool = False,
    now: datetime | None = None,
) -> list[TickerRun]:
    """Ingest each ticker and log the run. ``now`` is injectable for tests."""
    now = now or datetime.now(UTC)
    cfg = settings.data
    target_end = last_completed_session(now, cfg.calendar)
    if cfg.end_date:
        target_end = min(target_end, cfg.end_date)

    run_id = now.strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:6]
    runs = []
    for ticker in tickers or cfg.tickers:
        run = TickerRun(run_id=run_id, ticker=ticker.upper(), started_at=_naive_utc(now))
        try:
            _ingest_one(run, settings, store, source, target_end, full_refresh, now)
        except Exception as exc:  # isolate: record and move on to the next ticker
            log.exception("%s: ingest failed", run.ticker)
            run.status, run.message = "failed", f"{type(exc).__name__}: {exc}"
        run.finished_at = _naive_utc(datetime.now(UTC))
        _log_run(store, run, now)
        runs.append(run)
        log.info(
            "%s: %s %s, wrote %d rows (%d rejected), %d errors / %d warnings %s",
            run.ticker,
            run.mode or "-",
            run.status,
            run.rows_written,
            run.rows_rejected,
            run.dq_errors,
            run.dq_warnings,
            run.message,
        )
    return runs


def _ingest_one(
    run: TickerRun,
    settings: Settings,
    store: Storage,
    source: PriceSource,
    target_end: date,
    full_refresh: bool,
    now: datetime,
) -> None:
    cfg = settings.data
    ticker = run.ticker
    last = store.latest_dates("prices_daily").get(ticker)

    if full_refresh or last is None:
        run.mode = "backfill"
    elif last >= target_end:
        run.mode = "up_to_date"
    else:
        run.mode = "incremental"

    issues = [pd.DataFrame(columns=ISSUE_COLUMNS)]

    if run.mode in ("backfill", "incremental"):
        if run.mode == "backfill":
            start = cfg.start_date
        else:
            start = previous_session(last, cfg.overlap_days - 1, cfg.calendar)
        fetched = _fetch(source, ticker, start, target_end)
        run.fetch_start, run.fetch_end = start, target_end

        if run.mode == "incremental" and _restated(store, ticker, fetched.prices, start, last, cfg):
            run.mode = "refresh"
            run.message = "history restated by source (split/dividend); re-fetched in full"
            start = cfg.start_date
            fetched = _fetch(source, ticker, start, target_end)
            run.fetch_start = start

        run.rows_fetched = len(fetched.prices)
        if fetched.prices.empty:
            if run.mode == "incremental":
                run.status, run.message = "warn", "source returned no new bars"
            else:
                raise ValueError("source returned no data (unknown or delisted ticker?)")

        clean, row_issues = check_rows(fetched.prices, cfg.calendar)
        issues.append(row_issues)
        run.rows_rejected = len(fetched.prices) - len(clean)

        prices = _stamp(clean, source.name, now)
        actions = _stamp(fetched.actions, source.name, now)
        if run.mode == "incremental":
            run.rows_written = store.upsert("prices_daily", prices)
            store.upsert("corporate_actions", actions)
        else:
            run.rows_written = store.replace_ticker("prices_daily", ticker, prices)
            store.replace_ticker("corporate_actions", ticker, actions)

    issues.append(
        check_series(
            store.read("prices_daily", ticker),
            store.read("corporate_actions", ticker),
            expected_last=target_end,
            max_daily_move=cfg.max_daily_move,
            calendar=cfg.calendar,
        )
    )
    run.issues = pd.concat([i for i in issues if not i.empty] or issues, ignore_index=True)
    run.dq_errors = int((run.issues["severity"] == "error").sum())
    run.dq_warnings = int((run.issues["severity"] == "warn").sum())
    if run.dq_errors:
        run.status = "error"
    elif run.dq_warnings and run.status == "ok":
        run.status = "warn"


def _fetch(source: PriceSource, ticker: str, start: date, end: date) -> FetchResult:
    """Fetch and trim to [start, end]. Sources may return a partial bar for today or
    extra rows around the edges; nothing outside the window is kept."""
    res = source.fetch(ticker, start, end)
    p, a = res.prices, res.actions
    p = p[(p["date"] >= start) & (p["date"] <= end)].reset_index(drop=True)
    if not a.empty:
        a = a[(a["date"] >= start) & (a["date"] <= end)].reset_index(drop=True)
    return FetchResult(p, a)


def _restated(
    store: Storage, ticker: str, fetched: pd.DataFrame, start: date, last: date, cfg: DataSettings
) -> bool:
    """Do re-fetched overlap bars differ from what we stored?

    Compares sessions strictly before the latest stored bar. That latest bar is skipped
    because its numbers can legitimately firm up after the close (late prints), and the
    upsert will overwrite it anyway. A real restatement shifts *all* earlier bars, so
    excluding one doesn't hide it.
    """
    stored = store.read("prices_daily", ticker, start=start, end=last)
    stored = stored[stored["date"] < last]
    both = stored.merge(fetched, on="date", suffixes=("_old", "_new"))
    if both.empty:
        return False
    for col in ("close", "adj_close"):
        old, new = both[f"{col}_old"].astype(float), both[f"{col}_new"].astype(float)
        rel = ((new - old).abs() / old.abs()).max()
        if rel > cfg.restatement_tolerance:
            log.info("%s: %s restated by up to %.4f%%", ticker, col, rel * 100)
            return True
    return False


def _stamp(df: pd.DataFrame, source: str, now: datetime) -> pd.DataFrame:
    return df.assign(source=source, ingested_at=_naive_utc(now))


def _log_run(store: Storage, run: TickerRun, now: datetime) -> None:
    store.upsert("ingest_runs", pd.DataFrame([run.record()]))
    if not run.issues.empty:
        issues = run.issues.assign(run_id=run.run_id, detected_at=_naive_utc(now))
        store.append("dq_issues", issues)


def _naive_utc(ts: datetime) -> datetime:
    """DuckDB TIMESTAMP has no timezone; store UTC wall-clock time."""
    return ts.astimezone(UTC).replace(tzinfo=None)
