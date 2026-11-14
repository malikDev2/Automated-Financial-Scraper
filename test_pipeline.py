import pandas as pd

from fin_scraper import lake, pipeline

from conftest import MONDAY, SATURDAY


def test_object_key_is_hive_partitioned():
    key = lake.object_key("raw/", "orders", MONDAY)
    assert key == "raw/orders/dt=2024-06-03/orders.parquet"


def test_run_batch_to_lake_writes_four_parquet_files(settings):
    result = pipeline.run_batch_to_lake(MONDAY, settings)
    assert result is not None
    assert set(result["locations"]) == {"prices", "products", "customers", "orders"}
    for path in result["locations"].values():
        assert path.endswith(".parquet")
    orders = pd.read_parquet(result["locations"]["orders"])
    assert len(orders) == result["counts"]["orders"] > 0
    assert str(orders["order_ts"].dtype).startswith("datetime64[us")  # Snowflake-safe precision


def test_rerunning_a_day_overwrites_instead_of_duplicating(settings):
    first = pipeline.run_batch_to_lake(MONDAY, settings)
    second = pipeline.run_batch_to_lake(MONDAY, settings)
    assert first["locations"] == second["locations"]
    assert len(pd.read_parquet(second["locations"]["orders"])) == second["counts"]["orders"]


def test_weekend_is_skipped_cleanly(settings):
    assert pipeline.run_batch_to_lake(SATURDAY, settings) is None
    assert not settings.local_lake_dir.exists()
