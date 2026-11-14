"""CLI:  python -m fin_scraper <run|backfill|bootstrap|serve>"""
from __future__ import annotations

import argparse
import logging
from datetime import date

from .config import get_settings
from .utils import business_days


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="fin_scraper", description="Automated-Financial-Scraper ETL")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run the pipeline for one trading day")
    run.add_argument("--date", type=date.fromisoformat, help="YYYY-MM-DD (default: previous business day)")
    run.add_argument("--export-excel", action="store_true", help="also build the Excel report")

    bf = sub.add_parser("backfill", help="run every business day in a range")
    bf.add_argument("--start", type=date.fromisoformat, required=True)
    bf.add_argument("--end", type=date.fromisoformat, required=True)

    sub.add_parser("bootstrap", help="create Snowflake staging/core/reporting/ops objects")
    sub.add_parser("serve", help="register the Prefect deployment and run on its schedule")
    args = parser.parse_args(argv)

    settings = get_settings()
    from .flows import daily_etl

    if args.command == "run":
        print(daily_etl(run_date=args.date, export_excel=args.export_excel))
    elif args.command == "backfill":
        for d in business_days(args.start, args.end):
            print(daily_etl(run_date=d))
    elif args.command == "bootstrap":
        from .warehouse import bootstrap_snowflake

        bootstrap_snowflake(settings)
        print("Snowflake objects created.")
    elif args.command == "serve":
        from prefect.schedules import Cron

        # 06:00 New York, Tue-Sat: each run loads the previous business day
        daily_etl.serve(
            name="daily-financial-etl",
            schedule=Cron("0 6 * * 2-6", timezone="America/New_York"),
            tags=["finance", "etl"],
        )


if __name__ == "__main__":
    main()
