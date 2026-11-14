from datetime import date

import pytest

from fin_scraper.config import Settings

MONDAY = date(2024, 6, 3)
SATURDAY = date(2024, 6, 1)


@pytest.fixture
def settings(tmp_path):
    return Settings(
        tickers=("AAPL", "MSFT", "NVDA", "JPM"),
        price_provider="synthetic",
        orders_per_day=200,
        customer_count=150,
        random_seed=7,
        load_target="local",
        local_lake_dir=tmp_path / "lake",
        export_dir=tmp_path / "exports",
    )
