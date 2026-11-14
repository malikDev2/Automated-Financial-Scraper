"""Prefect flow: daily-financial-etl.

extract (parallel) -> transform -> quality gate -> land in S3 -> Snowflake staging
-> merge dimensions -> load facts -> post-load checks -> audit -> (optional) Excel report
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

import pandas as pd
from prefect import flow, get_run_logger, task

from . import extract, pipeline, quality, report, simulator
from .config import get_settings
from .lake import write_to_lake
from .pipeline import Batch
from .utils import previous_business_day
from .warehouse import Warehouse

RETRY = dict(retries=3, retry_delay_seconds=[5, 20, 60])


# ----------------------------------------------------------------------------- extract
@task(name="extract-prices", **RETRY)
def extract_prices_task(run_date: date) -> pd.DataFrame:
    return extract.extract_prices(run_date, get_settings())


@task(name="extract-products", **RETRY)
def extract_products_task() -> pd.DataFrame:
    return extract.extract_products(get_settings())


@task(name="extract-customers", **RETRY)
def extract_customers_task(run_date: date) -> pd.DataFrame:
    return simulator.extract_customers(run_date, get_settings())


@task(name="extract-orders", **RETRY)
def extract_orders_task(run_date: date, prices: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    return simulator.extract_orders(run_date, prices, customers, get_settings())


# ----------------------------------------------------------------------------- transform / validate / land
@task(name="transform")
def transform_task(run_date: date, prices, products, customers, orders) -> Batch:
    return pipeline.transform_batch(run_date, prices, products, customers, orders)


@task(name="quality-gate")
def validate_task(batch: Batch) -> dict:
    logger = get_run_logger()
    results = pipeline.validate(batch, get_settings())
    for res in results:
        (logger.info if res.passed else logger.warning)(str(res))
    quality.enforce(results)
    return {"checks": len(results), "warnings": sum(1 for r in results if not r.passed)}


@task(name="land-in-lake", **RETRY)
def land_task(batch: Batch) -> dict[str, str]:
    return write_to_lake(batch.frames(), batch.run_date, get_settings())


# ----------------------------------------------------------------------------- snowflake
@task(name="snowflake-stage-load", retries=2, retry_delay_seconds=[15, 60])
def stage_task(run_date: date, counts: dict[str, int]) -> None:
    with Warehouse(get_settings()) as wh:
        wh.run_file("10_load_staging.sql", run_date)
        for entity, expected in counts.items():
            loaded = wh.scalar(f"SELECT COUNT(*) FROM staging.stg_{entity}")
            if loaded != expected:
                raise quality.DataQualityError([quality.CheckResult(
                    f"staging_rowcount:{entity}", "snowflake", False, quality.CRITICAL,
                    abs(loaded - expected), f"parquet has {expected}, staging has {loaded}")])


@task(name="merge-dimensions", retries=1, retry_delay_seconds=30)
def merge_dimensions_task(run_date: date) -> None:
    with Warehouse(get_settings()) as wh:
        wh.run_file("20_merge_dimensions.sql", run_date)


@task(name="load-facts", retries=1, retry_delay_seconds=30)
def load_facts_task(run_date: date) -> None:
    with Warehouse(get_settings()) as wh:
        wh.run_file("30_load_facts.sql", run_date)


@task(name="post-load-checks")
def post_load_checks_task(run_date: date) -> dict:
    logger = get_run_logger()
    with Warehouse(get_settings()) as wh:
        results = quality.run_sql_checks(wh, run_date)
    for res in results:
        (logger.info if res.passed else logger.warning)(str(res))
    quality.enforce(results)
    return {"checks": len(results), "warnings": sum(1 for r in results if not r.passed)}


@task(name="write-audit")
def audit_task(run_id: str, run_date: date, status: str, counts: dict[str, int],
               started_at: datetime, error: str | None = None) -> None:
    with Warehouse(get_settings()) as wh:
        wh.write_audit(run_id, run_date, status, counts, started_at, error)


@task(name="export-excel")
def export_excel_task(run_date: date) -> str:
    return str(report.export_daily_report(run_date, get_settings()))


# ----------------------------------------------------------------------------- flow
@flow(name="daily-financial-etl", log_prints=True)
def daily_etl(run_date: date | None = None, export_excel: bool = False) -> dict:
    """Ingest one trading day. `run_date` defaults to the previous business day."""
    settings = get_settings()
    logger = get_run_logger()
    run_date = run_date or previous_business_day()
    run_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc).replace(tzinfo=None)
    logger.info("Starting ETL for %s (provider=%s, target=%s, snowflake=%s)", run_date,
                settings.price_provider, settings.load_target, settings.load_snowflake)

    prices_f = extract_prices_task.submit(run_date)
    products_f = extract_products_task.submit()
    customers_f = extract_customers_task.submit(run_date)

    prices_raw = prices_f.result()
    products_raw, customers_raw = products_f.result(), customers_f.result()
    if prices_raw.empty:
        logger.warning("No market data for %s (weekend or exchange holiday). Nothing to load.", run_date)
        return {"run_date": run_date.isoformat(), "status": "SKIPPED"}

    orders_raw = extract_orders_task(run_date, prices_raw, customers_raw)
    batch = transform_task(run_date, prices_raw, products_raw, customers_raw, orders_raw)
    counts = batch.row_counts()
    summary: dict = {"run_date": run_date.isoformat(), "counts": counts}

    try:
        summary["quality_gate"] = validate_task(batch)
        summary["locations"] = land_task(batch)
        if settings.load_snowflake:
            stage_task(run_date, counts)
            merge_dimensions_task(run_date)
            load_facts_task(run_date)
            summary["post_load"] = post_load_checks_task(run_date)
    except Exception as exc:
        if settings.load_snowflake:
            try:
                audit_task(run_id, run_date, "FAILED", counts, started_at, str(exc))
            except Exception as audit_exc:  # never mask the original failure
                logger.error("Could not write failure audit row: %s", audit_exc)
        raise

    if settings.load_snowflake:
        audit_task(run_id, run_date, "SUCCESS", counts, started_at)
        if export_excel:
            summary["excel_report"] = export_excel_task(run_date)

    summary["status"] = "SUCCESS"
    logger.info("Finished %s: %s", run_date, counts)
    return summary
