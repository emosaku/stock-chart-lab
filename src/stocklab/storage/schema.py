"""Backend-neutral table definitions.

Each table lists its columns with a logical type and its primary key. Backends translate
the logical types to their own (DuckDB now, BigQuery later), so the schema is written once.
Tables for later phases are added here when their phase is built.
"""

from dataclasses import dataclass

# Logical type -> DuckDB type. A BigQuery backend adds its own mapping
# (DATE -> DATE, DOUBLE -> FLOAT64, BIGINT -> INT64, VARCHAR -> STRING, ...).
DUCKDB_TYPES = {
    "string": "VARCHAR",
    "date": "DATE",
    "timestamp": "TIMESTAMP",
    "float": "DOUBLE",
    "int": "BIGINT",
}


@dataclass(frozen=True)
class Table:
    name: str
    columns: dict[str, str]  # column name -> logical type, in table order
    primary_key: tuple[str, ...] = ()
    # The column that per-ticker partitions and date-range reads filter on.
    date_column: str | None = None

    @property
    def column_names(self) -> list[str]:
        return list(self.columns)


PRICES_DAILY = Table(
    name="prices_daily",
    columns={
        "ticker": "string",
        "date": "date",
        # Yahoo's open/high/low/close are already adjusted for *splits* but not for
        # dividends. adj_close is adjusted for both, so it is the column to use when
        # comparing prices across years or computing returns.
        "open": "float",
        "high": "float",
        "low": "float",
        "close": "float",
        "adj_close": "float",
        "volume": "int",
        "source": "string",
        "ingested_at": "timestamp",
    },
    primary_key=("ticker", "date"),
    date_column="date",
)

CORPORATE_ACTIONS = Table(
    name="corporate_actions",
    columns={
        "ticker": "string",
        "date": "date",
        # "split": value is the ratio (20.0 = each share became 20).
        # "dividend": value is cash paid per share on the ex-dividend date.
        "action_type": "string",
        "value": "float",
        "source": "string",
        "ingested_at": "timestamp",
    },
    primary_key=("ticker", "date", "action_type"),
    date_column="date",
)

# One row per ticker per `stocklab ingest` run: what was fetched and what happened.
INGEST_RUNS = Table(
    name="ingest_runs",
    columns={
        "run_id": "string",
        "ticker": "string",
        "started_at": "timestamp",
        "finished_at": "timestamp",
        "mode": "string",  # backfill | incremental | refresh | up_to_date
        "fetch_start": "date",
        "fetch_end": "date",
        "rows_fetched": "int",
        "rows_written": "int",
        "rows_rejected": "int",
        "dq_errors": "int",
        "dq_warnings": "int",
        "status": "string",  # ok | warn | error | failed
        "message": "string",
    },
    primary_key=("run_id", "ticker"),
)

# Data-quality findings, one row per issue per run. Append-only, so the history of
# what each run saw is kept; "current state" is the latest run_id per ticker.
DQ_ISSUES = Table(
    name="dq_issues",
    columns={
        "run_id": "string",
        "ticker": "string",
        "check_name": "string",
        "severity": "string",  # error (row rejected) | warn (row kept, flagged)
        "date": "date",
        "detail": "string",
        "detected_at": "timestamp",
    },
    date_column="date",
)

# Technical indicators in long ("tidy") form: one row per ticker, day and indicator.
# Long rather than one column per indicator so that changing a window in settings.yaml
# (say SMA 20 -> 30) changes rows, not the table schema. Consumers pivot to wide with
# features.load_indicators(). Recomputed in full per ticker on every run, because a
# split restates the price history they're computed from.
INDICATORS = Table(
    name="indicators",
    columns={
        "ticker": "string",
        "date": "date",
        "indicator": "string",  # e.g. sma_50, rsi, macd_hist, bb_upper
        "value": "float",
        "params": "string",  # e.g. "length=14", so stored values say how they were made
        "computed_at": "timestamp",
    },
    primary_key=("ticker", "date", "indicator"),
    date_column="date",
)

TABLES: dict[str, Table] = {
    t.name: t for t in (PRICES_DAILY, CORPORATE_ACTIONS, INGEST_RUNS, DQ_ISSUES, INDICATORS)
}
