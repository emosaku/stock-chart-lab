# Phase 0: Engineering Decisions

Scope: project scaffolding, tooling, and environment. No pipeline logic yet.

## Component split mirrors the requested separation and the phases

`src/stocklab/` contains `storage/`, `ingestion/`, `features/`, `signals/`,
`backtesting/`, `models/` and `app/`. The proposal asked for ingestion, features,
signals, backtesting, models and app to be kept separate. `storage/` is the one
addition.

**Why:** each phase builds one component, so module boundaries match the roadmap. A
separate `storage/` package keeps database access in a single place. That matters for
the GCP move (next decision).

## All DB access goes through `storage/`; backend chosen by env var

Other components pass pandas DataFrames to `storage/` and get DataFrames back. None
of them opens a database connection. The `STORAGE_BACKEND` setting is `duckdb` now
and will be `bigquery` after migration.

**Why:** this is the main thing that keeps the BigQuery move small. If SQL and
connection handling were spread across ingestion, signals and the app, migrating would
mean touching every module. With one storage package, it means writing a second
backend and switching one setting.

## DuckDB over SQLite

**Why:**
- DuckDB is a column store built for analytical scans, like "all GOOG closes", which
  is the main workload here. SQLite is row-oriented and built for transactions.
- DuckDB's SQL dialect, with window functions and `QUALIFY`, is close to BigQuery's.
- It reads and writes Parquet natively, so the migration can export Parquet and
  bulk-load it into BigQuery.
- It's a single file with no server, like SQLite.

## Two config sources: `.env` for *where*, `settings.yaml` for *what*

- `.env` and environment variables hold the DB path, storage backend and GCP project.
  These change between a laptop and Cloud Run.
- `config/settings.yaml` holds tickers, date ranges and the per-phase parameters. It
  is committed and stays the same across environments. It's validated by pydantic
  when loaded, so a typo fails immediately instead of three phases later.

**Why:** Cloud Run configures containers through environment variables. Mixing
analysis parameters into them would make runs hard to reproduce. Sections for later
phases are empty placeholders for now and get typed models when their phase is built.
This avoids guessing parameters now.

## Each pipeline step will be a CLI command

From Phase 1 on, `stocklab ingest`, `stocklab indicators` and the other steps are
idempotent batch commands. Idempotent means running a command twice gives the same
result as running it once.

**Why:** a batch CLI command maps directly onto a Cloud Run job, and Cloud Scheduler
can trigger it daily. That needs no code changes, only a container. An orchestrator
like Airflow or Composer would be overkill for a five-step daily batch, and Composer
runs all the time and costs money even when idle.

## No GCP APIs enabled yet

The GCP project exists, but nothing is enabled.

**Why:** phases 1–6 run locally. Every enabled API is something to reason about and
possibly pay for. The README lists which APIs Phase 7 will enable.

## Optional dependency groups per phase

The core install covers Phase 1: `pandas`, `yfinance`, `duckdb`, `pyyaml`, `pydantic`
and `python-dotenv`. Later phases have extras: `indicators` (pandas-ta), `backtest`
(vectorbt), `ml` (scikit-learn, xgboost), `app` (streamlit, plotly) and
`gcp` (google-cloud-bigquery, db-dtypes). The `all` extra installs everything
except `gcp`.

**Why:** vectorbt pulls in numba and xgboost is large. CI and the eventual ingestion
container only need the core. All the extras were installed in Phase 0 to check they
work together on Python 3.12, which turned up two issues:
- **pandas-ta pinned to `>=0.4`.** The 0.3.x line imports `numpy.NaN`, which numpy 2
  removed. The verified version is 0.4.71b0.
- **plotly pinned to `>=6,<7`.** vectorbt 1.0.0 registers a `scattermapbox` chart
  template that plotly 7 removed, so `import vectorbt` crashes on plotly 7.1. Version
  6.3.1 works. Remove the pin once vectorbt supports plotly 7.

## Tests never hit the network

Tests use small, frozen price fixtures. yfinance is mocked at the ingestion boundary.

**Why:** tests that depend on Yahoo being up and returning the same data twice are
unreliable, and CI runs without credentials. A separate manual command will check
the live yfinance connection.
