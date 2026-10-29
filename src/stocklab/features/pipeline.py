"""``stocklab indicators``: recompute indicators for every ticker from stored prices.

Always a full recompute per ticker, never incremental. A split restates the whole
price history, and an EMA carries every earlier price inside it, so patching only
new days could leave old values on a stale basis. It's ~15 years x ~16 indicators per
ticker and takes well under a second, so correctness wins over cleverness. Idempotent:
the same prices and settings give the same rows.
"""

import logging
from datetime import UTC, datetime

import pandas as pd

from stocklab.config import Settings
from stocklab.features.indicators import compute_indicators, to_wide
from stocklab.storage import Storage

log = logging.getLogger(__name__)


def run_indicators(
    settings: Settings,
    store: Storage,
    *,
    tickers: list[str] | None = None,
    now: datetime | None = None,
) -> list[dict]:
    now = now or datetime.now(UTC)
    stamp = now.astimezone(UTC).replace(tzinfo=None)
    results = []
    for ticker in tickers or settings.data.tickers:
        ticker = ticker.upper()
        prices = store.read("prices_daily", ticker)
        if prices.empty:
            log.warning("%s: no prices stored; run `stocklab ingest` first", ticker)
            results.append({"ticker": ticker, "bars": 0, "rows_written": 0, "status": "no_prices"})
            continue
        long = compute_indicators(prices, settings.indicators).assign(computed_at=stamp)
        n = store.replace_ticker("indicators", ticker, long)
        results.append(
            {
                "ticker": ticker,
                "bars": len(prices),
                "indicators": long["indicator"].nunique(),
                "rows_written": n,
                "last_date": prices["date"].max(),
                "status": "ok",
            }
        )
        log.info("%s: %d indicator rows over %d bars", ticker, n, len(prices))
    return results


def load_indicators(store: Storage, ticker: str, start=None, end=None) -> pd.DataFrame:
    """Prices joined with their indicators, one row per day: the frame Phase 3 signals
    and the Phase 6 dashboard read."""
    prices = store.read("prices_daily", ticker, start=start, end=end)
    wide = to_wide(store.read("indicators", ticker, start=start, end=end))
    if wide.empty:
        return prices
    return prices.merge(wide, on=["ticker", "date"], how="left")
