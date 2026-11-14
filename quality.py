"""Data-quality framework.

Two layers:
  1. DataFrame checks run *before* anything is landed in S3 (bad data never reaches the lake).
  2. SQL checks run *after* the Snowflake load (reconciliation + star-schema integrity).

Critical failures stop the run; warnings are logged and recorded.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

CRITICAL = "critical"
WARN = "warn"


@dataclass(frozen=True)
class CheckResult:
    name: str
    table: str
    passed: bool
    severity: str
    failed: int
    detail: str = ""

    def __str__(self) -> str:
        status = "PASS" if self.passed else f"FAIL[{self.severity}]"
        extra = f" ({self.failed} rows) {self.detail}" if not self.passed else ""
        return f"{status} {self.table}.{self.name}{extra}"


class DataQualityError(RuntimeError):
    def __init__(self, failures: Sequence[CheckResult]):
        self.failures = list(failures)
        super().__init__("Data quality gate failed:\n  " + "\n  ".join(str(f) for f in self.failures))


def _res(name: str, table: str, failed: int, severity: str = CRITICAL, detail: str = "") -> CheckResult:
    failed = int(failed)
    return CheckResult(name, table, failed == 0, severity, failed, detail)


# --------------------------------------------------------------------------- generic checks
def not_null(df: pd.DataFrame, table: str, columns: Iterable[str], severity: str = CRITICAL) -> list[CheckResult]:
    out = []
    for c in columns:
        if c not in df.columns:
            out.append(_res(f"not_null:{c}", table, max(len(df), 1), severity, "column missing"))
        else:
            out.append(_res(f"not_null:{c}", table, df[c].isna().sum(), severity))
    return out


def unique(df: pd.DataFrame, table: str, columns: list[str], severity: str = CRITICAL) -> CheckResult:
    return _res(f"unique:{'+'.join(columns)}", table, df.duplicated(subset=columns).sum(), severity)


def in_range(df: pd.DataFrame, table: str, column: str, min_value=None, max_value=None,
             severity: str = CRITICAL) -> CheckResult:
    bad = pd.Series(False, index=df.index)
    if min_value is not None:
        bad |= df[column] < min_value
    if max_value is not None:
        bad |= df[column] > max_value
    return _res(f"range:{column}", table, bad.sum(), severity, f"expected [{min_value}, {max_value}]")


def accepted_values(df: pd.DataFrame, table: str, column: str, allowed: Iterable[str],
                    severity: str = CRITICAL) -> CheckResult:
    bad = ~df[column].isin(list(allowed)) & df[column].notna()
    return _res(f"accepted_values:{column}", table, bad.sum(), severity)


def foreign_key(df: pd.DataFrame, table: str, column: str, ref: pd.DataFrame, ref_column: str,
                severity: str = CRITICAL) -> CheckResult:
    bad = ~df[column].isin(ref[ref_column]) & df[column].notna()
    return _res(f"fk:{column}->{ref_column}", table, bad.sum(), severity)


def min_rows(df: pd.DataFrame, table: str, minimum: int, severity: str = CRITICAL) -> CheckResult:
    return _res("min_rows", table, int(len(df) < minimum), severity, f"got {len(df)}, need >= {minimum}")


# --------------------------------------------------------------------------- domain checks
def ohlc_consistent(prices: pd.DataFrame) -> CheckResult:
    hi, lo = prices["high_price"], prices["low_price"]
    bad = (
        (hi < lo)
        | (hi < prices[["open_price", "close_price"]].max(axis=1) - 1e-6)
        | (lo > prices[["open_price", "close_price"]].min(axis=1) + 1e-6)
    )
    return _res("ohlc_consistent", "prices", bad.sum())


def ticker_coverage(prices: pd.DataFrame, expected: Sequence[str], min_ratio: float = 0.8) -> list[CheckResult]:
    missing = sorted(set(expected) - set(prices["ticker"]))
    ratio = 1 - len(missing) / max(len(expected), 1)
    return [
        _res("ticker_coverage_min", "prices", int(ratio < min_ratio), CRITICAL,
             f"{ratio:.0%} of expected tickers present"),
        _res("ticker_coverage_complete", "prices", len(missing), WARN, f"missing: {missing}" if missing else ""),
    ]


def net_amount_reconciles(orders: pd.DataFrame, tolerance: float = 0.01) -> CheckResult:
    sign = np.where(orders["side"] == "BUY", 1.0, -1.0)
    expected = orders["gross_amount"] + sign * orders["fees"]
    return _res("net_amount_reconciles", "orders", ((expected - orders["net_amount"]).abs() > tolerance).sum())


def exec_price_within_day_range(orders: pd.DataFrame, prices: pd.DataFrame, slack: float = 0.005) -> CheckResult:
    merged = orders.merge(prices[["ticker", "low_price", "high_price"]], on="ticker", how="left")
    bad = (merged["exec_price"] < merged["low_price"] * (1 - slack)) | (
        merged["exec_price"] > merged["high_price"] * (1 + slack)
    )
    return _res("exec_price_within_day_range", "orders", bad.sum(), WARN)


# --------------------------------------------------------------------------- batch gate
def validate_batch(prices: pd.DataFrame, products: pd.DataFrame, customers: pd.DataFrame,
                   orders: pd.DataFrame, run_date: date, expected_tickers: Sequence[str]) -> list[CheckResult]:
    r: list[CheckResult] = []

    # prices
    r += not_null(prices, "prices", ["ticker", "trade_date", "open_price", "high_price", "low_price",
                                     "close_price", "volume"])
    r += [
        unique(prices, "prices", ["ticker", "trade_date"]),
        in_range(prices, "prices", "close_price", min_value=0.01),
        in_range(prices, "prices", "volume", min_value=0),
        ohlc_consistent(prices),
        _res("trade_date_matches_batch", "prices", (prices["trade_date"] != run_date).sum()),
        min_rows(prices, "prices", 1),
    ]
    r += ticker_coverage(prices, expected_tickers)

    # products
    r += not_null(products, "products", ["ticker", "company_name"])
    r += [unique(products, "products", ["ticker"]),
          foreign_key(prices, "prices", "ticker", products, "ticker")]

    # customers
    r += not_null(customers, "customers", ["customer_id", "segment", "country"])
    r += [unique(customers, "customers", ["customer_id"]),
          accepted_values(customers, "customers", "segment", ["retail", "professional", "institutional"])]

    # orders
    r += not_null(orders, "orders", ["order_id", "customer_id", "ticker", "side", "status", "quantity",
                                     "exec_price", "order_ts"])
    r += [
        min_rows(orders, "orders", 1),
        unique(orders, "orders", ["order_id"]),
        accepted_values(orders, "orders", "side", ["BUY", "SELL"]),
        accepted_values(orders, "orders", "status", ["FILLED", "CANCELLED", "REJECTED"]),
        in_range(orders, "orders", "quantity", min_value=1),
        in_range(orders, "orders", "exec_price", min_value=0.01),
        in_range(orders, "orders", "fees", min_value=0),
        foreign_key(orders, "orders", "customer_id", customers, "customer_id"),
        foreign_key(orders, "orders", "ticker", products, "ticker"),
        net_amount_reconciles(orders),
        exec_price_within_day_range(orders, prices),
    ]
    return r


def enforce(results: Sequence[CheckResult]) -> None:
    """Log everything, raise if any critical check failed."""
    for res in results:
        (log.info if res.passed else log.warning)("%s", res)
    critical = [x for x in results if not x.passed and x.severity == CRITICAL]
    if critical:
        raise DataQualityError(critical)


# --------------------------------------------------------------------------- post-load SQL checks
@dataclass(frozen=True)
class SqlCheck:
    name: str
    severity: str
    sql: str  # returns ONE number: count of violations (0 = pass). {run_date} is an ISO date.


POST_LOAD_CHECKS: tuple[SqlCheck, ...] = (
    SqlCheck("fact_orders_matches_staging", CRITICAL, """
        SELECT ABS(
            (SELECT COUNT(*) FROM staging.stg_orders)
          - (SELECT COUNT(*) FROM core.fact_orders WHERE batch_date = '{run_date}'::DATE)
        )"""),
    SqlCheck("fact_prices_matches_staging", CRITICAL, """
        SELECT ABS(
            (SELECT COUNT(*) FROM staging.stg_prices)
          - (SELECT COUNT(*) FROM core.fact_daily_prices WHERE batch_date = '{run_date}'::DATE)
        )"""),
    SqlCheck("filled_notional_matches_staging", CRITICAL, """
        SELECT IFF(ABS(
            (SELECT COALESCE(SUM(gross_amount), 0) FROM staging.stg_orders)
          - (SELECT COALESCE(SUM(gross_amount), 0) FROM core.fact_orders WHERE batch_date = '{run_date}'::DATE)
        ) > 0.01, 1, 0)"""),
    SqlCheck("fact_orders_no_duplicate_order_id", CRITICAL, """
        SELECT COUNT(*) FROM (
            SELECT order_id FROM core.fact_orders GROUP BY order_id HAVING COUNT(*) > 1
        )"""),
    SqlCheck("fact_orders_no_orphan_customers", CRITICAL, """
        SELECT COUNT(*) FROM core.fact_orders f
        LEFT JOIN core.dim_customers c ON c.customer_key = f.customer_key
        WHERE f.batch_date = '{run_date}'::DATE AND c.customer_key IS NULL"""),
    SqlCheck("fact_orders_no_orphan_products", CRITICAL, """
        SELECT COUNT(*) FROM core.fact_orders f
        LEFT JOIN core.dim_products p ON p.product_key = f.product_key
        WHERE f.batch_date = '{run_date}'::DATE AND p.product_key IS NULL"""),
    SqlCheck("fact_orders_valid_filled_amounts", CRITICAL, """
        SELECT COUNT(*) FROM core.fact_orders
        WHERE batch_date = '{run_date}'::DATE AND status = 'FILLED'
          AND (quantity <= 0 OR gross_amount <= 0 OR fees < 0)"""),
    SqlCheck("fact_orders_net_amount_reconciles", CRITICAL, """
        SELECT COUNT(*) FROM core.fact_orders
        WHERE batch_date = '{run_date}'::DATE
          AND ABS(net_amount - (gross_amount + IFF(side = 'BUY', fees, -fees))) > 0.01"""),
    SqlCheck("fact_orders_date_key_matches_batch", CRITICAL, """
        SELECT COUNT(*) FROM core.fact_orders
        WHERE batch_date = '{run_date}'::DATE
          AND date_key <> TO_NUMBER(TO_CHAR(batch_date, 'YYYYMMDD'))"""),
    SqlCheck("dim_customers_unique_business_key", CRITICAL, """
        SELECT COUNT(*) FROM (
            SELECT customer_id FROM core.dim_customers GROUP BY customer_id HAVING COUNT(*) > 1
        )"""),
    SqlCheck("dim_products_unique_business_key", CRITICAL, """
        SELECT COUNT(*) FROM (
            SELECT ticker FROM core.dim_products GROUP BY ticker HAVING COUNT(*) > 1
        )"""),
    SqlCheck("dim_products_no_unknown_sector", WARN, """
        SELECT COUNT(*) FROM core.dim_products WHERE sector = 'Unknown'"""),
)


def run_sql_checks(warehouse, run_date: date) -> list[CheckResult]:
    results = []
    for chk in POST_LOAD_CHECKS:
        failed = warehouse.scalar(chk.sql.format(run_date=run_date.isoformat()))
        results.append(_res(chk.name, "snowflake", failed, chk.severity))
    return results
