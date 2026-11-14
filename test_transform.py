import pandas as pd

from fin_scraper import extract, simulator
from fin_scraper.transform import MIN_FEE, ORDERS_OUT, transform_orders, transform_prices

from conftest import MONDAY


def _customers():
    return pd.DataFrame({"customer_id": ["C1", "C2"], "segment": ["retail", "institutional"]})


def _raw_orders():
    ts = pd.Timestamp("2024-06-03 10:00:00")
    return pd.DataFrame([
        {"order_id": "A", "customer_id": "C1", "ticker": "aapl", "side": "BUY", "status": "FILLED",
         "quantity": 100, "exec_price": 200.0, "order_ts": ts},
        {"order_id": "B", "customer_id": "C2", "ticker": "AAPL", "side": "SELL", "status": "FILLED",
         "quantity": 1000, "exec_price": 200.0, "order_ts": ts},
        {"order_id": "C", "customer_id": "C1", "ticker": "AAPL", "side": "BUY", "status": "CANCELLED",
         "quantity": 10, "exec_price": 200.0, "order_ts": ts},
        {"order_id": "D", "customer_id": "C1", "ticker": "AAPL", "side": "BUY", "status": "FILLED",
         "quantity": 1, "exec_price": 5.0, "order_ts": ts},
    ])


def test_fees_and_net_amounts():
    out = transform_orders(_raw_orders(), _customers(), MONDAY).set_index("order_id")
    assert list(transform_orders(_raw_orders(), _customers(), MONDAY).columns) == ORDERS_OUT
    # retail BUY: gross 20,000, fee 0.10% = 20, net = gross + fee
    assert out.loc["A", "gross_amount"] == 20_000
    assert out.loc["A", "fees"] == 20
    assert out.loc["A", "net_amount"] == 20_020
    # institutional SELL: gross 200,000, fee 0.02% = 40, net = gross - fee
    assert out.loc["B", "fees"] == 40
    assert out.loc["B", "net_amount"] == 199_960


def test_non_filled_orders_move_no_money():
    out = transform_orders(_raw_orders(), _customers(), MONDAY).set_index("order_id")
    assert out.loc["C", ["gross_amount", "fees", "net_amount"]].tolist() == [0, 0, 0]


def test_minimum_fee_applies():
    out = transform_orders(_raw_orders(), _customers(), MONDAY).set_index("order_id")
    assert out.loc["D", "fees"] == MIN_FEE


def test_tickers_normalised_and_batch_columns_added():
    out = transform_orders(_raw_orders(), _customers(), MONDAY)
    assert set(out["ticker"]) == {"AAPL"}
    assert (out["batch_date"] == MONDAY).all()
    assert (out["order_date"] == MONDAY).all()


def test_prices_get_change_pct_and_batch_date(settings):
    out = transform_prices(extract.extract_prices(MONDAY, settings), MONDAY)
    expected = ((out["close_price"] - out["open_price"]) / out["open_price"] * 100).round(4)
    assert (out["price_change_pct"] - expected).abs().max() < 1e-3
    assert (out["batch_date"] == MONDAY).all()
