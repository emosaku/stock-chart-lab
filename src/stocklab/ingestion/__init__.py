"""Ingestion: daily OHLCV price history from yfinance into storage.

OHLCV = Open, High, Low, Close, Volume -- one "bar" per ticker per trading day.
Backfills from settings.data.start_date, then on reruns fetches only days after the
latest stored date per ticker (incremental). Also records splits/dividends and runs
data-quality checks (missing trading days, nulls, duplicates, unexplained price jumps).
Built in Phase 1. In the cloud it becomes a Cloud Run job on a Cloud Scheduler cron.
"""
