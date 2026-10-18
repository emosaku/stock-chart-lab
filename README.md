# Stock Chart Lab

## Overview

A learning project for stock chart analysis and prediction. It pulls about 15 years of
daily prices for a configurable list of tickers (GOOG, META and AMZN to start). From
those prices it computes the technical indicators traders use, detects classic chart
signals, and backtests each signal to see whether trading it would have beaten simply
buying and holding. It also trains ML models with strict walk-forward validation and
shows all of this in a Streamlit dashboard.

The project is aimed at someone who knows data engineering but is new to trading. Each
trading concept is explained briefly where it first appears, in code comments and in
[docs/trading-concepts.md](docs/trading-concepts.md).

## Honest scope

- **Not investment advice, and not a trading system.** There's no live trading or broker
  connection. The output is analysis plus a backtest of what *would have* happened.
- **Daily bars only**, from yfinance. yfinance is an unofficial Yahoo Finance scraper,
  fine for research but with no uptime or accuracy guarantee. All price data goes
  through one ingestion module, so it can be replaced with a paid feed later.
- **The ML is expected to struggle.** Predicting next-day direction from price history
  alone barely beats a coin flip in most published work. Phase 5 reports results
  against a naive baseline either way, including when the model loses.
- **Personal scale.** A few tickers and a local DuckDB file. The design is ready for
  GCP, but nothing runs in the cloud until the migration phase.

## Architecture

```
                 config/settings.yaml  (tickers, dates, parameters)
                             │
  yfinance ──► ingestion ──► ┌──────────────────────────────────────────┐
  (daily OHLCV,  incremental │ storage  (DuckDB now → BigQuery later)   │
   splits)       + DQ checks │                                          │
                             │  prices_daily      corporate_actions     │
          features ◄────────►│  indicators                              │
          signals  ◄────────►│  signals                                 │
          backtesting ◄─────►│  backtest_results                        │
          models   ◄────────►│  predictions                             │
                             └───────────────────┬──────────────────────┘
                                                 │ read-only
                                                 ▼
                                        app (Streamlit dashboard)

  Later, on GCP:  Cloud Scheduler ─► Cloud Run jobs (one per CLI step) ─► BigQuery
                                     Cloud Run service (dashboard) ◄──────┘
```

Each stage is a batch step. It reads tables, computes, and writes its own table, and
every step goes through `storage/`. The steps form a pipeline, ingest → indicators →
signals → backtest/train, and each will be a `stocklab <step>` CLI command. The same
commands later run as Cloud Run jobs triggered by Cloud Scheduler. The dashboard
never computes anything; it only reads what the pipeline stored.

**Avoiding lookahead bias.** Lookahead bias means accidentally using information from
the future, and it is the main way stock research fools itself. These rules apply
across the whole codebase:

- An indicator or feature for day *t* uses only data up to and including day *t*.
- Backtests trade on the bar after a signal fires.
- ML targets are shifted forward explicitly.
- Models are validated walk-forward only, never with random splits.

## Phase roadmap

| Phase | Description | Status |
|---|---|---|
| 0 | Scaffolding, tooling, environment | **Complete** |
| 1 | Data pipeline: yfinance → DuckDB, incremental updates, data-quality checks | Not started |
| 2 | Indicators: SMA/EMA 20/50/200, RSI, MACD, Bollinger Bands, ATR, volume MA | Not started |
| 3 | Signals: golden/death cross, RSI extremes, MACD crosses, BB breakouts, support/resistance | Not started |
| 4 | Backtesting: vectorbt per signal, with costs, vs. buy-and-hold | Not started |
| 5 | ML: next-day direction and 5-day volatility, LR baseline and XGBoost, walk-forward | Not started |
| 6 | Dashboard: Streamlit candlesticks, overlays, signals, backtests, predictions | Not started |
| 7 | GCP migration: BigQuery, Cloud Run jobs and Scheduler, Cloud Run dashboard | Later |

## Project layout

```
config/settings.yaml   tickers, date ranges, per-phase parameters
src/stocklab/
├── config.py          .env (where things live) + settings.yaml (what to analyse)
├── storage/           schema and all DB access; DuckDB backend, BigQuery later
├── ingestion/         yfinance fetch, incremental upsert, data-quality checks
├── features/          pandas-ta indicators, ML feature builders
├── signals/           rule-based signal detection, support/resistance
├── backtesting/       vectorbt backtests, metrics, buy-and-hold comparison
├── models/            walk-forward validation, baselines, logistic regression, XGBoost
└── app/               Streamlit dashboard (read-only)
tests/                 mirrors src/; uses frozen fixtures and never hits the network
docs/                  decisions log, trading-concepts glossary
```

## Setup

```bash
git clone https://github.com/emosaku/stock-chart-lab.git
cd stock-chart-lab
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,all]"      # or just ".[dev]" for the Phase 1 core
cp .env.example .env              # defaults work locally; set GCP_PROJECT_ID for cloud work
pytest
```

Python 3.12 is required. pandas-ta 0.4+ needs it, and some ML libraries don't support
3.13 or later yet. The cloud dependencies are in the separate `gcp` extra, installed
with `pip install -e ".[gcp]"`. You only need `gcloud auth application-default login`
once the GCP migration starts.

## GCP

- **Project:** `stock-chart-lab-emk`, region `us-west1`
- **APIs enabled now:** none. Phases 1–6 run entirely locally.
- **APIs enabled at migration (Phase 7):**
  - `bigquery.googleapis.com` for the tables
  - `run.googleapis.com`, `artifactregistry.googleapis.com` and
    `cloudbuild.googleapis.com` for the jobs and dashboard
  - `cloudscheduler.googleapis.com` for daily ingestion
  - `storage.googleapis.com` for model artifacts

All of these scale to zero or sit within the free tier at this size.
