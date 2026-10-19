"""DuckDB backend: a single local file, used until the GCP migration."""

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

from stocklab.storage.schema import DUCKDB_TYPES, TABLES, Table


class DuckDBStorage:
    def __init__(self, path: str | Path):
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self.con = duckdb.connect(self.path)

    # -- schema -------------------------------------------------------------------------

    def init_schema(self) -> None:
        for table in TABLES.values():
            cols = [f"{name} {DUCKDB_TYPES[kind]}" for name, kind in table.columns.items()]
            if table.primary_key:
                cols.append(f"PRIMARY KEY ({', '.join(table.primary_key)})")
            self.con.execute(f"CREATE TABLE IF NOT EXISTS {table.name} ({', '.join(cols)})")

    # -- writes -------------------------------------------------------------------------

    def upsert(self, table: str, df: pd.DataFrame) -> int:
        t = _table(table)
        if not t.primary_key:
            raise ValueError(f"{table} has no primary key; use append()")
        return self._insert(t, df, "INSERT OR REPLACE")

    def append(self, table: str, df: pd.DataFrame) -> int:
        return self._insert(_table(table), df, "INSERT")

    def replace_ticker(self, table: str, ticker: str, df: pd.DataFrame) -> int:
        t = _table(table)
        self.con.begin()
        try:
            self.con.execute(f"DELETE FROM {t.name} WHERE ticker = ?", [ticker])
            n = self._insert(t, df, "INSERT")
            self.con.commit()
        except Exception:
            self.con.rollback()
            raise
        return n

    def _insert(self, t: Table, df: pd.DataFrame, verb: str) -> int:
        if df.empty:
            return 0
        cols = t.column_names
        missing = set(cols) - set(df.columns)
        if missing:
            raise ValueError(f"{t.name}: missing columns {sorted(missing)}")
        incoming = df[cols]
        self.con.register("_incoming", incoming)
        try:
            col_list = ", ".join(cols)
            self.con.execute(f"{verb} INTO {t.name} ({col_list}) SELECT {col_list} FROM _incoming")
        finally:
            self.con.unregister("_incoming")
        return len(incoming)

    # -- reads --------------------------------------------------------------------------

    def read(
        self,
        table: str,
        tickers: str | Iterable[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> pd.DataFrame:
        t = _table(table)
        where, params = [], []
        if tickers is not None:
            tickers = [tickers] if isinstance(tickers, str) else list(tickers)
            where.append(f"ticker IN ({', '.join('?' * len(tickers))})")
            params += tickers
        if (start or end) and not t.date_column:
            raise ValueError(f"{table} has no date column to filter on")
        if start:
            where.append(f"{t.date_column} >= ?")
            params.append(start)
        if end:
            where.append(f"{t.date_column} <= ?")
            params.append(end)
        sql = f"SELECT * FROM {t.name}"
        if where:
            sql += " WHERE " + " AND ".join(where)
        order = [c for c in ("ticker", t.date_column) if c and c in t.columns]
        if order:
            sql += " ORDER BY " + ", ".join(order)
        df = self.con.execute(sql, params).df()
        # DuckDB returns DATE columns as datetime64; give callers plain dates, as stored.
        for col, kind in t.columns.items():
            if kind == "date" and col in df:
                df[col] = pd.to_datetime(df[col]).dt.date
        return df

    def latest_dates(self, table: str = "prices_daily") -> dict[str, date]:
        t = _table(table)
        rows = self.con.execute(
            f"SELECT ticker, max({t.date_column}) FROM {t.name} GROUP BY ticker"
        ).fetchall()
        return {ticker: d for ticker, d in rows}

    def close(self) -> None:
        self.con.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _table(name: str) -> Table:
    try:
        return TABLES[name]
    except KeyError:
        raise ValueError(f"unknown table {name!r}") from None
