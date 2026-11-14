"""Thin Snowflake wrapper: connection handling, SQL-file execution, audit logging."""
from __future__ import annotations

import io
import logging
from datetime import date, datetime

import pandas as pd

from .config import Settings
from .utils import render_sql

log = logging.getLogger(__name__)


class Warehouse:
    def __init__(self, settings: Settings):
        settings.require_snowflake()
        self.settings = settings
        self._conn = None

    def __enter__(self) -> "Warehouse":
        import snowflake.connector

        s = self.settings
        self._conn = snowflake.connector.connect(
            account=s.snowflake_account,
            user=s.snowflake_user,
            password=s.snowflake_password,
            role=s.snowflake_role,
            warehouse=s.snowflake_warehouse,
            database=s.snowflake_database,
            session_parameters={"QUERY_TAG": "fin_scraper_etl"},
        )
        return self

    def __exit__(self, *exc) -> None:
        if self._conn is not None:
            self._conn.close()

    # ------------------------------------------------------------------ execution
    def execute(self, sql: str) -> list[tuple]:
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            return cur.fetchall()
        finally:
            cur.close()

    def scalar(self, sql: str):
        rows = self.execute(sql)
        return rows[0][0] if rows else 0

    def run_script(self, script: str) -> None:
        from snowflake.connector.util_text import split_statements

        for stmt, _ in split_statements(io.StringIO(script), remove_comments=True):
            if stmt.strip():
                log.debug("SQL> %s", stmt.strip().splitlines()[0])
                self.execute(stmt)

    def run_file(self, filename: str, run_date: date | None = None) -> None:
        params = {"run_date": run_date.isoformat()} if run_date else {}
        log.info("Running %s", filename)
        self.run_script(render_sql(self.settings.sql_dir / filename, **params))

    def query_df(self, sql: str) -> pd.DataFrame:
        cur = self._conn.cursor()
        try:
            cur.execute(sql)
            cols = [c[0].lower() for c in cur.description]
            return pd.DataFrame(cur.fetchall(), columns=cols)
        finally:
            cur.close()

    # ------------------------------------------------------------------ audit
    def write_audit(self, run_id: str, run_date: date, status: str, counts: dict[str, int],
                    started_at: datetime, error: str | None = None) -> None:
        cur = self._conn.cursor()
        try:
            cur.execute(
                """INSERT INTO ops.etl_run_audit
                   (run_id, run_date, status, rows_prices, rows_products, rows_customers, rows_orders,
                    started_at, finished_at, error_message)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP(), %s)""",
                (run_id, run_date, status, counts.get("prices"), counts.get("products"),
                 counts.get("customers"), counts.get("orders"), started_at, (error or "")[:4000] or None),
            )
        finally:
            cur.close()


def bootstrap_snowflake(settings: Settings) -> None:
    """Create staging/core/reporting/ops objects. Idempotent. (00_setup_infra.sql is run once by an admin.)"""
    with Warehouse(settings) as wh:
        for f in ("01_ddl_staging.sql", "02_ddl_core.sql", "03_ddl_reporting.sql"):
            wh.run_file(f)
