"""Orchestrator-agnostic pipeline steps (used by the CLI, tests, and the Airflow DAG)."""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone

import pandas as pd

from . import quality, simulator, transform
from .config import Settings
from .extract import extract_prices, extract_products
from .lake import write_to_lake
from .quality import CheckResult, DataQualityError
from .warehouse import Warehouse

log = logging.getLogger(__name__)


@dataclass
class Batch:
    run_date: date
    prices: pd.DataFrame
    products: pd.DataFrame
    customers: pd.DataFrame
    orders: pd.DataFrame

    def frames(self) -> dict[str, pd.DataFrame]:
        return {"prices": self.prices, "products": self.products,
                "customers": self.customers, "orders": self.orders}

    def row_counts(self) -> dict[str, int]:
        return {k: len(v) for k, v in self.frames().items()}


def transform_batch(run_date: date, prices_raw: pd.DataFrame, products_raw: pd.DataFrame,
                    customers_raw: pd.DataFrame, orders_raw: pd.DataFrame) -> Batch:
    customers = transform.transform_customers(customers_raw, run_date)
    return Batch(
        run_date=run_date,
        prices=transform.transform_prices(prices_raw, run_date),
        products=transform.transform_products(products_raw, run_date),
        customers=customers,
        orders=transform.transform_orders(orders_raw, customers, run_date),
    )


def validate(batch: Batch, settings: Settings) -> list[CheckResult]:
    return quality.validate_batch(batch.prices, batch.products, batch.customers, batch.orders,
                                  batch.run_date, settings.tickers)


def build_batch(run_date: date, settings: Settings) -> Batch | None:
    """Extract + transform. Returns None when the market was closed (no prices)."""
    prices_raw = extract_prices(run_date, settings)
    if prices_raw.empty:
        return None
    products_raw = extract_products(settings)
    customers_raw = simulator.extract_customers(run_date, settings)
    orders_raw = simulator.extract_orders(run_date, prices_raw, customers_raw, settings)
    return transform_batch(run_date, prices_raw, products_raw, customers_raw, orders_raw)


def run_batch_to_lake(run_date: date, settings: Settings) -> dict | None:
    """Extract -> transform -> quality gate -> land Parquet. Safe to re-run for the same date."""
    batch = build_batch(run_date, settings)
    if batch is None:
        log.warning("No market data for %s - skipping.", run_date)
        return None
    quality.enforce(validate(batch, settings))
    locations = write_to_lake(batch.frames(), run_date, settings)
    return {"run_date": run_date.isoformat(), "counts": batch.row_counts(), "locations": locations}


def load_batch_to_snowflake(run_date: date, settings: Settings, counts: dict[str, int],
                            run_id: str | None = None) -> list[CheckResult]:
    """S3 -> staging (COPY INTO) -> dimensions/facts (MERGE) -> post-load checks -> audit row."""
    run_id = run_id or str(uuid.uuid4())
    started = datetime.now(timezone.utc).replace(tzinfo=None)
    with Warehouse(settings) as wh:
        try:
            wh.run_file("10_load_staging.sql", run_date)
            for entity, expected in counts.items():
                loaded = wh.scalar(f"SELECT COUNT(*) FROM staging.stg_{entity}")
                if loaded != expected:
                    raise DataQualityError([CheckResult(
                        f"staging_rowcount:{entity}", "snowflake", False, quality.CRITICAL,
                        abs(loaded - expected), f"parquet has {expected}, staging has {loaded}")])
            wh.run_file("20_merge_dimensions.sql", run_date)
            wh.run_file("30_load_facts.sql", run_date)
            results = quality.run_sql_checks(wh, run_date)
            quality.enforce(results)
        except Exception as exc:
            wh.write_audit(run_id, run_date, "FAILED", counts, started, str(exc))
            raise
        wh.write_audit(run_id, run_date, "SUCCESS", counts, started)
        return results
