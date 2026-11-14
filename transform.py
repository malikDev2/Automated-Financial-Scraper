"""Pure pandas transforms: raw extracts in, load-ready frames out."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

COMMISSION_RATE = {"retail": 0.0010, "professional": 0.0005, "institutional": 0.0002}
MIN_FEE = 1.00

PRICES_OUT = ["ticker", "trade_date", "open_price", "high_price", "low_price", "close_price",
              "adj_close_price", "volume", "price_change_pct", "batch_date"]
PRODUCTS_OUT = ["ticker", "company_name", "sector", "industry", "exchange", "currency", "batch_date"]
CUSTOMERS_OUT = ["customer_id", "full_name", "segment", "country", "signup_date", "batch_date"]
ORDERS_OUT = ["order_id", "customer_id", "ticker", "side", "status", "quantity", "exec_price",
              "gross_amount", "fees", "net_amount", "order_ts", "order_date", "batch_date"]


def transform_prices(raw: pd.DataFrame, run_date: date) -> pd.DataFrame:
    df = raw.copy()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    for col in ["open_price", "high_price", "low_price", "close_price", "adj_close_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").round(4)
    volume = pd.to_numeric(df["volume"], errors="coerce")
    df["volume"] = volume.astype("int64") if volume.notna().all() else volume
    df["price_change_pct"] = ((df["close_price"] - df["open_price"]) / df["open_price"] * 100).round(4)
    df = df.drop_duplicates(subset=["ticker", "trade_date"], keep="last")
    df["batch_date"] = run_date
    return df[PRICES_OUT].reset_index(drop=True)


def transform_products(raw: pd.DataFrame, run_date: date) -> pd.DataFrame:
    df = raw.copy()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    for col in ["company_name", "sector", "industry", "exchange", "currency"]:
        df[col] = df[col].fillna("Unknown").astype(str).str.strip().replace("", "Unknown")
    df = df.drop_duplicates(subset=["ticker"], keep="last")
    df["batch_date"] = run_date
    return df[PRODUCTS_OUT].reset_index(drop=True)


def transform_customers(raw: pd.DataFrame, run_date: date) -> pd.DataFrame:
    df = raw.copy()
    df["customer_id"] = df["customer_id"].astype(str).str.strip()
    df["full_name"] = df["full_name"].astype(str).str.strip()
    df["segment"] = df["segment"].astype(str).str.strip().str.lower()
    df["country"] = df["country"].astype(str).str.strip().str.upper()
    df = df.drop_duplicates(subset=["customer_id"], keep="last")
    df["batch_date"] = run_date
    return df[CUSTOMERS_OUT].reset_index(drop=True)


def transform_orders(raw: pd.DataFrame, customers: pd.DataFrame, run_date: date) -> pd.DataFrame:
    """Derive gross/fees/net. Only FILLED orders move money; fees depend on customer segment."""
    df = raw.copy()
    if df.empty:
        return pd.DataFrame(columns=ORDERS_OUT)

    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df["side"] = df["side"].astype(str).str.strip().str.upper()
    df["status"] = df["status"].astype(str).str.strip().str.upper()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").astype("int64")
    df["exec_price"] = pd.to_numeric(df["exec_price"], errors="coerce").round(4)
    df["order_ts"] = pd.to_datetime(df["order_ts"])

    df = df.merge(customers[["customer_id", "segment"]], on="customer_id", how="left")
    filled = df["status"].eq("FILLED")
    rate = df["segment"].map(COMMISSION_RATE).fillna(COMMISSION_RATE["retail"])

    df["gross_amount"] = np.where(filled, df["quantity"] * df["exec_price"], 0.0).round(4)
    df["fees"] = np.where(filled, np.maximum(df["gross_amount"] * rate, MIN_FEE), 0.0).round(4)
    df["net_amount"] = np.where(
        df["side"].eq("BUY"), df["gross_amount"] + df["fees"], df["gross_amount"] - df["fees"]
    ).round(4)
    df["order_date"] = df["order_ts"].dt.date
    df["batch_date"] = run_date

    df = df.drop_duplicates(subset=["order_id"], keep="last")
    return df[ORDERS_OUT].reset_index(drop=True)
