# Phase 1: Data Pipeline

Online version (with the update-mode diagram): https://claude.ai/code/artifact/15bf4371-04ae-4de1-aa8f-5d94cfd81816

Scope: yfinance → DuckDB, incremental updates, data-quality checks, and the first
`stocklab` CLI commands.

## What was built

| Module | Role |
|---|---|
| `storage/schema.py` | Backend-neutral table definitions (columns, logical types, primary keys) |
| `storage/base.py` | The `Storage` protocol: `upsert`, `append`, `replace_ticker`, `read`, `latest_dates` |
| `storage/duckdb_store.py` | DuckDB implementation |
| `ingestion/source.py` | `PriceSource` protocol, `YahooSource`, yfinance → our column names |
| `ingestion/calendar.py` | NYSE trading sessions and "last completed session" |
| `ingestion/quality.py` | Row checks (reject bad rows) and series checks (flag gaps and jumps) |
| `ingestion/pipeline.py` | Per-ticker backfill / incremental / refresh logic and run logging |
| `cli.py` | `stocklab ingest`, `stocklab status`, `stocklab check-source` |

Tables: `prices_daily`, `corporate_actions`, `ingest_runs`, `dq_issues`.

First live run (2026-10-18): GOOG and AMZN 4,223 bars each from 2010-01-04, META 3,624
from its 2012-05-18 listing. The full backfill takes about 1.5 s and finds no missing
sessions. There are two `large_move` warnings, both real: META +29.6% on 2013-07-25
(earnings) and −26.4% on 2022-02-03.

## Decisions

### Store both `close` and `adj_close`, and know what Yahoo's `close` really is

yfinance's `Close` is **already split-adjusted**. GOOG shows ~$112 the week before its
2022 20:1 split, not ~$2,250. `Adj Close` is additionally dividend-adjusted. Both are
kept. `adj_close` is the right series for returns and long-range comparisons. The
OHLC columns all share one basis, which matters for candlesticks and range-based
indicators like ATR. Phase 2 decides which one each indicator uses.

**Why not store truly raw prices?** Yahoo doesn't expose them through this API.
Reconstructing them from the split history would be our own derived data presented
as source data.

### Incremental with an overlap, and a full refresh when history is restated

The naive approach is to fetch only dates after the latest stored one and append them.
That breaks on the first split or dividend. Yahoo then back-adjusts the entire history,
so the stored rows and the new rows end up on different bases. A 20:1 split would show
as a 95% one-day crash at the join.

What the pipeline does instead:

1. Re-fetch the last `overlap_days` (5) stored sessions along with the new ones.
2. Compare re-fetched `close`/`adj_close` with stored values for those overlap days,
   excluding the newest stored day.
3. If anything differs by more than `restatement_tolerance` (0.01%), Yahoo has
   restated the history. Re-fetch that ticker in full and replace its rows in one
   transaction. Otherwise upsert.

The newest stored day is excluded from the comparison because its numbers can
legitimately firm up after the close. The upsert still overwrites it, so late
corrections land without triggering a refresh. A real restatement shifts *every*
earlier bar, so skipping one day doesn't hide it.

The tolerance comes from dividend sizes. A typical META or GOOG dividend moves
earlier `adj_close` values by about 0.05–0.1%, well above 0.01%. Yahoo's
float noise between identical fetches is far below that. The live incremental test
showed no false restatement.

### Never store today's partial bar

During market hours Yahoo returns a bar for today whose "close" is just the latest
trade. `last_completed_session(now)` uses the XNYS calendar's actual closing time,
including early closes, to cap every fetch. Running at 11am stores yesterday. Running
at 4:01pm ET stores today.

### Data-quality severity policy

- **Row checks run before writing. Failing rows are rejected (`error`)**:
  - nulls
  - prices ≤ 0
  - an inconsistent bar (high below open/close, low above them)
  - negative volume
  - duplicate dates
  - a bar dated on a day NYSE was closed

  One bad row would corrupt every rolling indicator that touches it, and a gap is
  visible and honest.
- **Series checks run after writing. Findings are flagged (`warn`)**:
  - missing sessions
  - stale data
  - one-day moves larger than `max_daily_move` (25%)

  These need a human, because big moves happen (META, 2022-02-03).
- **One series check is an `error`.** A large move on a split date that matches the
  split ratio means the source didn't back-adjust, so the data is certainly wrong.

Findings go to `dq_issues`, tagged with the run that saw them. A ticker's current
state is its latest run. Each run's summary goes to `ingest_runs`.

### NYSE calendar from `exchange_calendars`

"Every weekday" is the wrong standard for missing data. NYSE closes on Good Friday,
which isn't a federal holiday, and on one-off days like Hurricane Sandy (2012-10-29/30)
and national days of mourning (2025-01-09). `exchange_calendars` (XNYS) has all of
these. It's the one new core dependency.

### Failures are per ticker; exit code reflects outright failures

An unknown ticker or a network error marks that ticker `failed` and the run continues.
`stocklab ingest` exits 1 if any ticker failed, so Cloud Scheduler and Cloud Run will
show the job as failed. DQ warnings and rejected rows don't fail the job. They're
logged, and `stocklab status` surfaces them.

### The storage interface stays SQL-free

Callers use `upsert`, `append`, `replace_ticker`, `read(table, tickers, start, end)` and
`latest_dates`. Each maps to a single BigQuery operation: `MERGE`, an insert job,
`DELETE` + insert in a transaction, a parameterised `SELECT`, and `GROUP BY`. The
Phase 7 backend should be one new file.

## Known limitations

- Moving `start_date` *earlier* doesn't backfill automatically. Run
  `stocklab ingest --full-refresh`. The pipeline can't tell "the user wants older data"
  apart from "this stock didn't trade yet".
- yfinance can be rate-limited or change shape without notice. `stocklab check-source`
  is the quick live check. Tests never call it.
- GOOG's 2014-03-27 "2.002 split" is really the issue of Class C shares (GOOG) alongside
  Class A (GOOGL). Yahoo records it as a split, and the adjusted history handles it.

## How to run

```bash
stocklab check-source            # does yfinance answer? (network)
stocklab ingest                  # backfill first time, incremental after
stocklab ingest --tickers GOOG   # one ticker
stocklab ingest --full-refresh   # rebuild from start_date
stocklab status                  # coverage, splits/dividends, latest run, DQ findings
pytest                           # 40 tests, no network
```
