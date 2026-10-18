"""Storage: the only module that talks to the database.

Owns the table schema (prices_daily, corporate_actions, indicators, signals,
backtest_results, predictions) and read/write/upsert helpers. Every other component
passes DataFrames in and out of here and never opens a connection itself.
Backend is chosen by STORAGE_BACKEND: DuckDB locally (Phase 1), BigQuery after the
GCP migration. Swapping backends should only touch this package.
"""
