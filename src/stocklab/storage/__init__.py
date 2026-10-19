"""Storage: the only module that talks to the database.

Owns the table schema (prices_daily, corporate_actions, indicators, signals,
backtest_results, predictions) and read/write/upsert helpers. Every other component
passes DataFrames in and out of here and never opens a connection itself.
Backend is chosen by STORAGE_BACKEND: DuckDB locally (Phase 1), BigQuery after the
GCP migration. Swapping backends should only touch this package.
"""

from stocklab import config
from stocklab.storage.base import Storage
from stocklab.storage.schema import TABLES


def get_storage(path: str | None = None) -> Storage:
    """Open the configured backend with the schema in place."""
    if config.STORAGE_BACKEND == "duckdb":
        from stocklab.storage.duckdb_store import DuckDBStorage

        store = DuckDBStorage(path or config.resolve_path(config.STOCKLAB_DB_PATH))
    else:
        raise NotImplementedError(
            f"STORAGE_BACKEND={config.STORAGE_BACKEND!r} is not implemented yet "
            "(bigquery arrives with the GCP migration)"
        )
    store.init_schema()
    return store


__all__ = ["Storage", "TABLES", "get_storage"]
