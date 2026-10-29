"""``stocklab signals``: detect signal events for every ticker from stored indicators.

Full recompute per ticker, like indicators: signals derive from indicators, which are
themselves recomputed in full, so patching would only add ways to drift. Writes the
signals and price_levels tables; idempotent.
"""

import logging
from datetime import UTC, datetime

from stocklab.config import Settings
from stocklab.features import load_indicators
from stocklab.signals.detect import detect_signals
from stocklab.storage import Storage

log = logging.getLogger(__name__)


def run_signals(
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
        frame = load_indicators(store, ticker)
        if frame.empty or "rsi" not in frame:
            log.warning("%s: no indicators stored; run `stocklab indicators` first", ticker)
            results.append({"ticker": ticker, "signals": 0, "levels": 0, "status": "no_indicators"})
            continue
        signals, levels = detect_signals(frame, settings.signals)
        n_sig = store.replace_ticker("signals", ticker, signals.assign(computed_at=stamp))
        n_lev = store.replace_ticker(
            "price_levels",
            ticker,
            levels.drop(columns=["pivot_idx", "conf_idx"]).assign(computed_at=stamp),
        )
        last = signals.iloc[-1] if len(signals) else None
        results.append(
            {
                "ticker": ticker,
                "signals": n_sig,
                "levels": n_lev,
                "latest": f"{last.date} {last.signal}" if last is not None else "",
                "status": "ok",
            }
        )
        log.info("%s: %d signals, %d levels", ticker, n_sig, n_lev)
    return results
