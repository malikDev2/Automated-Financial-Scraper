"""Every SQL file and post-load check must at least parse as Snowflake SQL."""
from pathlib import Path

import pytest

from fin_scraper.quality import POST_LOAD_CHECKS
from fin_scraper.utils import render_sql

sqlglot = pytest.importorskip("sqlglot")
SQL_DIR = Path(__file__).resolve().parents[1] / "sql"
SQL_FILES = sorted(p for p in SQL_DIR.glob("*.sql"))


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.name)
def test_sql_file_parses(path):
    text = render_sql(path, run_date="2024-06-03") if "{run_date}" in path.read_text() else path.read_text()
    statements = sqlglot.parse(text, read="snowflake")
    assert [s for s in statements if s is not None], f"{path.name} produced no statements"


@pytest.mark.parametrize("check", POST_LOAD_CHECKS, ids=lambda c: c.name)
def test_post_load_check_parses(check):
    stmt = sqlglot.parse_one(check.sql.format(run_date="2024-06-03"), read="snowflake")
    assert stmt is not None


def test_star_schema_has_the_expected_tables():
    ddl = (SQL_DIR / "02_ddl_core.sql").read_text().lower()
    for table in ("fact_orders", "dim_customers", "dim_products", "dim_date", "fact_daily_prices"):
        assert f"core.{table}" in ddl
