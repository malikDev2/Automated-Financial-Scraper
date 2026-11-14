import pandas as pd
import pytest

from fin_scraper import pipeline, quality
from fin_scraper.quality import CRITICAL, WARN, DataQualityError

from conftest import MONDAY


@pytest.fixture
def batch(settings):
    b = pipeline.build_batch(MONDAY, settings)
    assert b is not None
    return b


def _failed(results, name_part):
    return [r for r in results if name_part in r.name and not r.passed]


def test_clean_batch_passes_every_critical_check(batch, settings):
    results = pipeline.validate(batch, settings)
    assert not [r for r in results if not r.passed and r.severity == CRITICAL]
    quality.enforce(results)  # must not raise


def test_duplicate_order_ids_are_caught(batch, settings):
    batch.orders = pd.concat([batch.orders, batch.orders.head(3)], ignore_index=True)
    with pytest.raises(DataQualityError) as err:
        quality.enforce(pipeline.validate(batch, settings))
    assert "unique:order_id" in str(err.value)


def test_null_keys_are_caught(batch, settings):
    batch.orders.loc[0, "customer_id"] = None
    assert _failed(pipeline.validate(batch, settings), "not_null:customer_id")


def test_orphan_customer_is_caught(batch, settings):
    batch.orders.loc[0, "customer_id"] = "C999999"
    assert _failed(pipeline.validate(batch, settings), "fk:customer_id")


def test_bad_side_and_negative_quantity_are_caught(batch, settings):
    batch.orders.loc[0, "side"] = "HOLD"
    batch.orders.loc[1, "quantity"] = -5
    results = pipeline.validate(batch, settings)
    assert _failed(results, "accepted_values:side")
    assert _failed(results, "range:quantity")


def test_broken_ohlc_is_caught(batch, settings):
    batch.prices.loc[0, "high_price"] = batch.prices.loc[0, "low_price"] - 1
    assert _failed(pipeline.validate(batch, settings), "ohlc_consistent")


def test_net_amount_mismatch_is_caught(batch, settings):
    idx = batch.orders.index[batch.orders["status"] == "FILLED"][0]
    batch.orders.loc[idx, "net_amount"] += 50
    assert _failed(pipeline.validate(batch, settings), "net_amount_reconciles")


def test_missing_tickers_warn_but_do_not_block_until_coverage_drops(batch, settings):
    batch.prices = batch.prices[batch.prices["ticker"] != "JPM"]  # 3 of 4 = 75% coverage
    results = pipeline.validate(batch, settings)
    coverage_warn = [r for r in results if r.name == "ticker_coverage_complete"][0]
    coverage_min = [r for r in results if r.name == "ticker_coverage_min"][0]
    assert not coverage_warn.passed and coverage_warn.severity == WARN
    assert not coverage_min.passed and coverage_min.severity == CRITICAL


def test_warning_only_failures_do_not_raise():
    quality.enforce([quality.CheckResult("x", "t", False, WARN, 3)])


def test_empty_orders_fail_the_gate(batch, settings):
    batch.orders = batch.orders.iloc[0:0]
    with pytest.raises(DataQualityError):
        quality.enforce(pipeline.validate(batch, settings))
