"""Environment-driven settings. Everything the pipeline needs comes from here."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TICKERS = "AAPL,MSFT,GOOGL,AMZN,NVDA,META,TSLA,JPM,V,JNJ,XOM,WMT"
PRICE_PROVIDERS = {"yahoo", "alphavantage", "synthetic"}
LOAD_TARGETS = {"s3", "local"}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_opt(name: str) -> str | None:
    raw = os.getenv(name)
    return raw.strip() if raw and raw.strip() else None


@dataclass(frozen=True)
class Settings:
    # market data
    tickers: tuple[str, ...] = tuple(DEFAULT_TICKERS.split(","))
    price_provider: str = "synthetic"
    alphavantage_api_key: str | None = None
    alphavantage_pause_seconds: float = 13.0
    # simulated order source
    orders_per_day: int = 500
    customer_count: int = 400
    random_seed: int = 42
    # data lake
    load_target: str = "local"
    s3_bucket: str | None = None
    s3_prefix: str = "raw"
    local_lake_dir: Path = PROJECT_ROOT / "data" / "lake"
    # snowflake
    load_snowflake: bool = False
    snowflake_account: str | None = None
    snowflake_user: str | None = None
    snowflake_password: str | None = None
    snowflake_role: str = "FIN_ETL_ROLE"
    snowflake_warehouse: str = "FIN_ETL_WH"
    snowflake_database: str = "FIN_SCRAPER"
    # paths
    sql_dir: Path = PROJECT_ROOT / "sql"
    export_dir: Path = PROJECT_ROOT / "data" / "exports"

    def __post_init__(self) -> None:
        if self.price_provider not in PRICE_PROVIDERS:
            raise ValueError(f"PRICE_PROVIDER must be one of {sorted(PRICE_PROVIDERS)}")
        if self.load_target not in LOAD_TARGETS:
            raise ValueError(f"LOAD_TARGET must be one of {sorted(LOAD_TARGETS)}")
        if self.load_target == "s3" and not self.s3_bucket:
            raise ValueError("S3_BUCKET is required when LOAD_TARGET=s3")
        if self.load_snowflake and self.load_target != "s3":
            raise ValueError("Snowflake loading reads from S3, so it needs LOAD_TARGET=s3")
        if self.price_provider == "alphavantage" and not self.alphavantage_api_key:
            raise ValueError("ALPHAVANTAGE_API_KEY is required for the alphavantage provider")

    def require_snowflake(self) -> None:
        missing = [
            name
            for name, value in {
                "SNOWFLAKE_ACCOUNT": self.snowflake_account,
                "SNOWFLAKE_USER": self.snowflake_user,
                "SNOWFLAKE_PASSWORD": self.snowflake_password,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError(f"Missing Snowflake settings: {', '.join(missing)}")

    @classmethod
    def from_env(cls) -> "Settings":
        tickers = tuple(
            t.strip().upper()
            for t in os.getenv("TICKERS", DEFAULT_TICKERS).split(",")
            if t.strip()
        )
        return cls(
            tickers=tickers,
            price_provider=os.getenv("PRICE_PROVIDER", "yahoo").strip().lower(),
            alphavantage_api_key=_env_opt("ALPHAVANTAGE_API_KEY"),
            orders_per_day=int(os.getenv("ORDERS_PER_DAY", "500")),
            customer_count=int(os.getenv("CUSTOMER_COUNT", "400")),
            random_seed=int(os.getenv("RANDOM_SEED", "42")),
            load_target=os.getenv("LOAD_TARGET", "local").strip().lower(),
            s3_bucket=_env_opt("S3_BUCKET"),
            s3_prefix=os.getenv("S3_PREFIX", "raw").strip("/"),
            local_lake_dir=Path(os.getenv("LOCAL_LAKE_DIR", str(PROJECT_ROOT / "data" / "lake"))),
            load_snowflake=_env_bool("LOAD_SNOWFLAKE", False),
            snowflake_account=_env_opt("SNOWFLAKE_ACCOUNT"),
            snowflake_user=_env_opt("SNOWFLAKE_USER"),
            snowflake_password=_env_opt("SNOWFLAKE_PASSWORD"),
            snowflake_role=os.getenv("SNOWFLAKE_ROLE", "FIN_ETL_ROLE"),
            snowflake_warehouse=os.getenv("SNOWFLAKE_WAREHOUSE", "FIN_ETL_WH"),
            snowflake_database=os.getenv("SNOWFLAKE_DATABASE", "FIN_SCRAPER"),
            sql_dir=Path(os.getenv("SQL_DIR", str(PROJECT_ROOT / "sql"))),
            export_dir=Path(os.getenv("EXPORT_DIR", str(PROJECT_ROOT / "data" / "exports"))),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
