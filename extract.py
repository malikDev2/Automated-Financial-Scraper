"""Market-data extraction. One provider interface, three implementations."""
from __future__ import annotations

import hashlib
import logging
import time
from datetime import date, timedelta
from typing import Protocol

import numpy as np
import pandas as pd
import requests

from .config import Settings

log = logging.getLogger(__name__)

PRICE_COLUMNS = [
    "ticker", "trade_date", "open_price", "high_price", "low_price",
    "close_price", "adj_close_price", "volume",
]
PRODUCT_COLUMNS = ["ticker", "company_name", "sector", "industry", "exchange", "currency"]


class PriceProvider(Protocol):
    def fetch_daily_prices(self, tickers: tuple[str, ...], run_date: date) -> pd.DataFrame: ...
    def fetch_products(self, tickers: tuple[str, ...]) -> pd.DataFrame: ...


# --------------------------------------------------------------------------- synthetic
# ticker: (company, sector, industry, exchange, reference price)
_REFERENCE: dict[str, tuple[str, str, str, str, float]] = {
    "AAPL": ("Apple Inc.", "Technology", "Consumer Electronics", "NASDAQ", 190.0),
    "MSFT": ("Microsoft Corporation", "Technology", "Software", "NASDAQ", 420.0),
    "GOOGL": ("Alphabet Inc.", "Communication Services", "Internet Content", "NASDAQ", 165.0),
    "AMZN": ("Amazon.com, Inc.", "Consumer Cyclical", "Internet Retail", "NASDAQ", 180.0),
    "NVDA": ("NVIDIA Corporation", "Technology", "Semiconductors", "NASDAQ", 120.0),
    "META": ("Meta Platforms, Inc.", "Communication Services", "Internet Content", "NASDAQ", 500.0),
    "TSLA": ("Tesla, Inc.", "Consumer Cyclical", "Auto Manufacturers", "NASDAQ", 240.0),
    "JPM": ("JPMorgan Chase & Co.", "Financial Services", "Banks", "NYSE", 200.0),
    "V": ("Visa Inc.", "Financial Services", "Credit Services", "NYSE", 275.0),
    "JNJ": ("Johnson & Johnson", "Healthcare", "Drug Manufacturers", "NYSE", 155.0),
    "XOM": ("Exxon Mobil Corporation", "Energy", "Oil & Gas", "NYSE", 115.0),
    "WMT": ("Walmart Inc.", "Consumer Defensive", "Discount Stores", "NYSE", 68.0),
}


def _stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(digest[:16], 16)


class SyntheticProvider:
    """Deterministic fake market. Weekends return nothing, like a closed exchange."""

    def __init__(self, seed: int = 42):
        self.seed = seed

    def fetch_daily_prices(self, tickers: tuple[str, ...], run_date: date) -> pd.DataFrame:
        if run_date.weekday() >= 5:
            return pd.DataFrame(columns=PRICE_COLUMNS)
        rows = []
        for t in tickers:
            base = _REFERENCE.get(t, ("", "", "", "", 100.0))[4]
            phase = _stable_seed(self.seed, t) % 100
            drift = 1 + 0.08 * np.sin(run_date.toordinal() / 45 + phase)
            rng = np.random.default_rng(_stable_seed(self.seed, t, run_date.isoformat()))
            close = base * drift * (1 + rng.normal(0, 0.01))
            open_ = close * (1 + rng.normal(0, 0.006))
            high = max(open_, close) * (1 + abs(rng.normal(0, 0.004)))
            low = min(open_, close) * (1 - abs(rng.normal(0, 0.004)))
            rows.append({
                "ticker": t, "trade_date": run_date,
                "open_price": open_, "high_price": high, "low_price": low,
                "close_price": close, "adj_close_price": close,
                "volume": int(rng.integers(5_000_000, 90_000_000)),
            })
        return pd.DataFrame(rows, columns=PRICE_COLUMNS)

    def fetch_products(self, tickers: tuple[str, ...]) -> pd.DataFrame:
        rows = []
        for t in tickers:
            name, sector, industry, exch, _ = _REFERENCE.get(t, (t, "Unknown", "Unknown", "Unknown", 0))
            rows.append({"ticker": t, "company_name": name or t, "sector": sector or "Unknown",
                         "industry": industry or "Unknown", "exchange": exch or "Unknown",
                         "currency": "USD"})
        return pd.DataFrame(rows, columns=PRODUCT_COLUMNS)


# --------------------------------------------------------------------------- yahoo
class YahooProvider:
    """Uses the yfinance package (unofficial Yahoo Finance client; no API key)."""

    def fetch_daily_prices(self, tickers: tuple[str, ...], run_date: date) -> pd.DataFrame:
        import yfinance as yf

        end = run_date + timedelta(days=1)
        rows = []
        for t in tickers:
            hist = yf.Ticker(t).history(
                start=run_date.isoformat(), end=end.isoformat(), auto_adjust=False, actions=False
            )
            if hist.empty or hist.index[0].date() != run_date:
                log.warning("No %s bar for %s (market closed or ticker delisted?)", t, run_date)
                continue
            r = hist.iloc[0]
            rows.append({
                "ticker": t, "trade_date": run_date,
                "open_price": float(r["Open"]), "high_price": float(r["High"]),
                "low_price": float(r["Low"]), "close_price": float(r["Close"]),
                "adj_close_price": float(r.get("Adj Close", r["Close"])),
                "volume": int(r["Volume"]),
            })
        return pd.DataFrame(rows, columns=PRICE_COLUMNS)

    def fetch_products(self, tickers: tuple[str, ...]) -> pd.DataFrame:
        import yfinance as yf

        rows = []
        for t in tickers:
            try:
                info = yf.Ticker(t).info or {}
            except Exception as exc:  # reference data is best-effort
                log.warning("Could not load reference data for %s: %s", t, exc)
                info = {}
            rows.append({
                "ticker": t,
                "company_name": info.get("longName") or t,
                "sector": info.get("sector") or "Unknown",
                "industry": info.get("industry") or "Unknown",
                "exchange": info.get("exchange") or "Unknown",
                "currency": info.get("currency") or "USD",
            })
        return pd.DataFrame(rows, columns=PRODUCT_COLUMNS)


# --------------------------------------------------------------------------- alpha vantage
class AlphaVantageProvider:
    """Official REST API. Free tier: 5 requests/minute, hence the pause between calls."""

    BASE_URL = "https://www.alphavantage.co/query"

    def __init__(self, api_key: str, pause_seconds: float = 13.0):
        self.api_key = api_key
        self.pause_seconds = pause_seconds

    def _get(self, params: dict) -> dict:
        for attempt in range(3):
            resp = requests.get(self.BASE_URL, params={**params, "apikey": self.api_key}, timeout=30)
            resp.raise_for_status()
            payload = resp.json()
            if "Note" in payload or "Information" in payload:
                log.warning("Alpha Vantage throttled: %s", payload.get("Note") or payload.get("Information"))
                time.sleep(self.pause_seconds * (attempt + 1))
                continue
            return payload
        raise RuntimeError("Alpha Vantage rate limit exceeded after 3 attempts")

    def fetch_daily_prices(self, tickers: tuple[str, ...], run_date: date) -> pd.DataFrame:
        rows = []
        for i, t in enumerate(tickers):
            if i:
                time.sleep(self.pause_seconds)
            payload = self._get({"function": "TIME_SERIES_DAILY", "symbol": t, "outputsize": "compact"})
            day = payload.get("Time Series (Daily)", {}).get(run_date.isoformat())
            if not day:
                log.warning("No %s bar for %s", t, run_date)
                continue
            close = float(day["4. close"])
            rows.append({
                "ticker": t, "trade_date": run_date,
                "open_price": float(day["1. open"]), "high_price": float(day["2. high"]),
                "low_price": float(day["3. low"]), "close_price": close,
                "adj_close_price": close,  # adjusted series is a premium endpoint
                "volume": int(day["5. volume"]),
            })
        return pd.DataFrame(rows, columns=PRICE_COLUMNS)

    def fetch_products(self, tickers: tuple[str, ...]) -> pd.DataFrame:
        rows = []
        for t in tickers:
            time.sleep(self.pause_seconds)
            try:
                info = self._get({"function": "OVERVIEW", "symbol": t})
            except Exception as exc:
                log.warning("Could not load overview for %s: %s", t, exc)
                info = {}
            rows.append({
                "ticker": t,
                "company_name": info.get("Name") or t,
                "sector": (info.get("Sector") or "Unknown").title(),
                "industry": (info.get("Industry") or "Unknown").title(),
                "exchange": info.get("Exchange") or "Unknown",
                "currency": info.get("Currency") or "USD",
            })
        return pd.DataFrame(rows, columns=PRODUCT_COLUMNS)


def get_provider(settings: Settings) -> PriceProvider:
    if settings.price_provider == "yahoo":
        return YahooProvider()
    if settings.price_provider == "alphavantage":
        return AlphaVantageProvider(settings.alphavantage_api_key or "", settings.alphavantage_pause_seconds)
    return SyntheticProvider(settings.random_seed)


def extract_prices(run_date: date, settings: Settings) -> pd.DataFrame:
    return get_provider(settings).fetch_daily_prices(settings.tickers, run_date)


def extract_products(settings: Settings) -> pd.DataFrame:
    return get_provider(settings).fetch_products(settings.tickers)
