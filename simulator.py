"""Stand-ins for the operational source systems (customer master + order feed).

There is no public brokerage order feed, so this module simulates one: deterministic customers and
trade orders priced off the *real* daily OHLC bars pulled by extract.py. To use a real source,
replace extract_customers / extract_orders with an API call or database export that returns the
same columns - nothing downstream changes.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import Settings
from .extract import _stable_seed

CUSTOMER_COLUMNS = ["customer_id", "full_name", "segment", "country", "signup_date"]
ORDER_COLUMNS = ["order_id", "customer_id", "ticker", "side", "status", "quantity", "exec_price", "order_ts"]

FIRST_NAMES = ["Ava", "Liam", "Noah", "Emma", "Mia", "Lucas", "Zoe", "Ethan", "Ivy", "Owen",
               "Nora", "Leo", "Maya", "Jack", "Ruby", "Finn", "Isla", "Theo", "Lena", "Kai"]
LAST_NAMES = ["Nguyen", "Patel", "Garcia", "Kim", "Silva", "Novak", "Cohen", "Ali", "Mori", "Berg",
              "Rossi", "Khan", "Lopez", "Meyer", "Dubois", "Singh", "Ortiz", "Haas", "Wong", "Reyes"]
SEGMENTS = ["retail", "professional", "institutional"]
SEGMENT_WEIGHTS = [0.80, 0.15, 0.05]
COUNTRIES = ["US", "GB", "CA", "DE", "AU", "SG", "JP", "FR"]
COUNTRY_WEIGHTS = [0.45, 0.12, 0.10, 0.08, 0.07, 0.07, 0.06, 0.05]
QUANTITY_RANGE = {"retail": (1, 50), "professional": (10, 500), "institutional": (500, 10_000)}
SIGNUP_ANCHOR = date(2022, 1, 1)


def extract_customers(run_date: date, settings: Settings) -> pd.DataFrame:
    """Customer master as of run_date (only customers who had signed up by then)."""
    rng = np.random.default_rng(settings.random_seed)
    n = settings.customer_count
    first = rng.choice(FIRST_NAMES, n)
    last = rng.choice(LAST_NAMES, n)
    df = pd.DataFrame({
        "customer_id": [f"C{i:06d}" for i in range(1, n + 1)],
        "full_name": [f"{f} {l}" for f, l in zip(first, last)],
        "segment": rng.choice(SEGMENTS, n, p=SEGMENT_WEIGHTS),
        "country": rng.choice(COUNTRIES, n, p=COUNTRY_WEIGHTS),
        "signup_date": [SIGNUP_ANCHOR + timedelta(days=int(o)) for o in rng.integers(0, 900, n)],
    })
    return df[df["signup_date"] <= run_date].reset_index(drop=True)[CUSTOMER_COLUMNS]


def extract_orders(run_date: date, prices: pd.DataFrame, customers: pd.DataFrame,
                   settings: Settings) -> pd.DataFrame:
    """One day of raw trade orders. exec_price is a point inside the day's real high/low range."""
    if prices.empty or customers.empty:
        return pd.DataFrame(columns=ORDER_COLUMNS)

    rng = np.random.default_rng(_stable_seed(settings.random_seed, "orders", run_date.isoformat()))
    n = max(1, int(rng.normal(settings.orders_per_day, settings.orders_per_day * 0.1)))
    bars = prices.set_index("ticker")
    tickers = list(bars.index)
    open_ts = pd.Timestamp(run_date) + pd.Timedelta(hours=9, minutes=30)

    rows = []
    for i in range(1, n + 1):
        cust = customers.iloc[int(rng.integers(0, len(customers)))]
        bar = bars.loc[tickers[int(rng.integers(0, len(tickers)))]]
        lo, hi = QUANTITY_RANGE[cust["segment"]]
        rows.append({
            "order_id": f"ORD-{run_date:%Y%m%d}-{i:06d}",
            "customer_id": cust["customer_id"],
            "ticker": bar.name,
            "side": "BUY" if rng.random() < 0.6 else "SELL",
            "status": rng.choice(["FILLED", "CANCELLED", "REJECTED"], p=[0.94, 0.04, 0.02]),
            "quantity": int(rng.integers(lo, hi + 1)),
            "exec_price": round(float(bar["low_price"] + rng.random() * (bar["high_price"] - bar["low_price"])), 4),
            "order_ts": open_ts + pd.Timedelta(seconds=int(rng.integers(0, int(6.5 * 3600)))),
        })
    return pd.DataFrame(rows, columns=ORDER_COLUMNS)
