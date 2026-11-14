"""End-to-end run of the real Prefect flow against a throwaway local Prefect API."""
import pandas as pd
import pytest

pytest.importorskip("prefect")
from prefect.testing.utilities import prefect_test_harness  # noqa: E402

from fin_scraper import config  # noqa: E402

from conftest import MONDAY, SATURDAY  # noqa: E402


@pytest.fixture
def local_env(monkeypatch, tmp_path):
    env = {
        "PRICE_PROVIDER": "synthetic", "LOAD_TARGET": "local", "LOAD_SNOWFLAKE": "false",
        "LOCAL_LAKE_DIR": str(tmp_path / "lake"), "TICKERS": "AAPL,MSFT,NVDA,JPM",
        "ORDERS_PER_DAY": "120", "CUSTOMER_COUNT": "80",
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    config.get_settings.cache_clear()
    yield tmp_path
    config.get_settings.cache_clear()


def test_flow_lands_a_trading_day_and_skips_a_weekend(local_env):
    from fin_scraper.flows import daily_etl

    with prefect_test_harness():
        ok = daily_etl(run_date=MONDAY)
        skipped = daily_etl(run_date=SATURDAY)

    assert ok["status"] == "SUCCESS"
    assert ok["counts"]["prices"] == 4
    assert ok["quality_gate"]["checks"] > 20
    assert len(pd.read_parquet(ok["locations"]["orders"])) == ok["counts"]["orders"]
    assert skipped["status"] == "SKIPPED"
