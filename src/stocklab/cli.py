"""``stocklab`` command line. Each subcommand is one idempotent batch step, so each can
later run unchanged as a Cloud Run job.

    stocklab ingest [--tickers GOOG META] [--full-refresh]
    stocklab status
    stocklab check-source [--ticker GOOG]
"""

import argparse
import logging
import sys
from datetime import UTC, datetime, timedelta

import pandas as pd

from stocklab.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="stocklab")
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="fetch daily prices into storage (incremental)")
    p.add_argument("--tickers", nargs="+", help="subset of configured tickers (default: all)")
    p.add_argument(
        "--full-refresh",
        action="store_true",
        help="re-fetch full history (use after moving start_date earlier)",
    )
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("status", help="coverage, latest run and data-quality summary")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("check-source", help="live check that yfinance answers (hits network)")
    p.add_argument("--ticker", default="GOOG")
    p.set_defaults(func=cmd_check_source)

    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # yfinance logs every HTTP hiccup at WARNING+; our own run log is the summary.
    logging.getLogger("yfinance").setLevel(logging.CRITICAL)
    return args.func(args)


def cmd_ingest(args) -> int:
    from stocklab.ingestion.pipeline import ingest
    from stocklab.ingestion.source import YahooSource
    from stocklab.storage import get_storage

    settings = get_settings()
    tickers = [t.upper() for t in args.tickers] if args.tickers else None
    unknown = set(tickers or []) - set(settings.data.tickers)
    if unknown:
        print(f"not in config/settings.yaml: {sorted(unknown)}", file=sys.stderr)
        return 2

    store = get_storage()
    try:
        runs = ingest(
            settings, store, YahooSource(), tickers=tickers, full_refresh=args.full_refresh
        )
    finally:
        store.close()

    table = pd.DataFrame([r.record() for r in runs])[
        [
            "ticker",
            "mode",
            "status",
            "rows_fetched",
            "rows_written",
            "rows_rejected",
            "dq_errors",
            "dq_warnings",
            "message",
        ]
    ]
    print(table.to_string(index=False))
    for r in runs:
        if not r.issues.empty:
            counts = r.issues.groupby(["severity", "check_name"]).size()
            print(f"\n{r.ticker} data-quality findings:")
            print(counts.to_string())
    # Non-zero exit when a ticker failed outright, so a scheduler marks the job failed.
    return 1 if any(r.status == "failed" for r in runs) else 0


def cmd_status(args) -> int:
    from stocklab.storage import get_storage

    store = get_storage()
    try:
        prices = store.read("prices_daily")
        runs = store.read("ingest_runs")
        issues = store.read("dq_issues")
        actions = store.read("corporate_actions")
    finally:
        store.close()

    if prices.empty:
        print("no prices stored yet -- run `stocklab ingest`")
        return 0

    coverage = prices.groupby("ticker").agg(
        first=("date", "min"), last=("date", "max"), bars=("date", "count")
    )
    if not actions.empty:
        n = actions.groupby(["ticker", "action_type"]).size().unstack(fill_value=0)
        coverage = coverage.join(n.add_suffix("s"), how="left").fillna(0)
    latest = runs.sort_values("started_at").groupby("ticker").tail(1).set_index("ticker")
    coverage = coverage.join(latest[["started_at", "mode", "status"]], how="left")
    print(coverage.to_string())

    if not issues.empty:
        last_run = latest["run_id"].to_dict()
        current = issues[issues.apply(lambda r: last_run.get(r.ticker) == r.run_id, axis=1)]
        if not current.empty:
            print("\nData-quality findings from each ticker's latest run:")
            print(current.groupby(["ticker", "severity", "check_name"]).size().to_string())
    return 0


def cmd_check_source(args) -> int:
    from stocklab.ingestion.source import YahooSource

    end = datetime.now(UTC).date()
    res = YahooSource().fetch(args.ticker.upper(), end - timedelta(days=10), end)
    if res.prices.empty:
        print(f"yfinance returned no bars for {args.ticker}", file=sys.stderr)
        return 1
    print(res.prices.to_string(index=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
