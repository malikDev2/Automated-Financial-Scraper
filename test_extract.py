from fin_scraper import extract, simulator
from fin_scraper.extract import PRICE_COLUMNS, SyntheticProvider
from fin_scraper.config import Settings

from conftest import MONDAY, SATURDAY


def test_synthetic_prices_are_deterministic(settings):
    a = extract.extract_prices(MONDAY, settings)
    b = extract.extract_prices(MONDAY, settings)
    assert a.equals(b)
    assert list(a.columns) == PRICE_COLUMNS
    assert set(a["ticker"]) == set(settings.tickers)


def test_weekend_returns_no_prices(settings):
    assert extract.extract_prices(SATURDAY, settings).empty


def test_synthetic_ohlc_is_internally_consistent(settings):
    df = extract.extract_prices(MONDAY, settings)
    assert (df["high_price"] >= df[["open_price", "close_price"]].max(axis=1)).all()
    assert (df["low_price"] <= df[["open_price", "close_price"]].min(axis=1)).all()


def test_products_cover_every_ticker(settings):
    df = extract.extract_products(settings)
    assert set(df["ticker"]) == set(settings.tickers)
    assert (df["sector"] != "Unknown").all()


def test_provider_factory():
    assert isinstance(extract.get_provider(Settings(price_provider="synthetic")), SyntheticProvider)
    assert isinstance(extract.get_provider(Settings(price_provider="yahoo")), extract.YahooProvider)


def test_customers_only_include_those_already_signed_up(settings):
    early = simulator.extract_customers(MONDAY, settings)
    assert (early["signup_date"] <= MONDAY).all()
    assert early["customer_id"].is_unique


def test_orders_are_deterministic_and_priced_inside_the_day_range(settings):
    prices = extract.extract_prices(MONDAY, settings)
    customers = simulator.extract_customers(MONDAY, settings)
    o1 = simulator.extract_orders(MONDAY, prices, customers, settings)
    o2 = simulator.extract_orders(MONDAY, prices, customers, settings)
    assert o1.equals(o2)
    assert o1["order_id"].is_unique
    merged = o1.merge(prices, on="ticker")
    assert (merged["exec_price"] >= merged["low_price"] - 1e-3).all()
    assert (merged["exec_price"] <= merged["high_price"] + 1e-3).all()
