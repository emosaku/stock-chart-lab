"""The storage interface every backend implements.

Callers pass and receive pandas DataFrames whose columns match ``schema.TABLES``. No
SQL crosses this boundary, which is what lets BigQuery replace DuckDB by adding one
backend class.
"""

from collections.abc import Iterable
from datetime import date
from typing import Protocol

import pandas as pd


class Storage(Protocol):
    def init_schema(self) -> None:
        """Create any missing tables. Safe to call on every run."""

    def upsert(self, table: str, df: pd.DataFrame) -> int:
        """Insert rows, replacing any with the same primary key. Returns rows written."""

    def append(self, table: str, df: pd.DataFrame) -> int:
        """Insert rows without key checks (for append-only logs). Returns rows written."""

    def replace_ticker(self, table: str, ticker: str, df: pd.DataFrame) -> int:
        """Atomically delete all of one ticker's rows and insert ``df`` in their place."""

    def read(
        self,
        table: str,
        tickers: str | Iterable[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        """Rows for the given tickers (all if None), optionally within [start, end]."""

    def latest_dates(self, table: str = "prices_daily") -> dict[str, date]:
        """Most recent date stored per ticker."""

    def close(self) -> None: ...
