"""Land Parquet files in the data lake (S3 in production, a local folder for dev/tests)."""
from __future__ import annotations

import io
import logging
from datetime import date
from pathlib import Path
from typing import Mapping

import pandas as pd

from .config import Settings

log = logging.getLogger(__name__)


def object_key(prefix: str, entity: str, run_date: date) -> str:
    """raw/orders/dt=2024-06-03/orders.parquet  - Hive-style partition, one file per entity per day."""
    return f"{prefix.strip('/')}/{entity}/dt={run_date.isoformat()}/{entity}.parquet"


def to_parquet_bytes(df: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    # microsecond timestamps: Snowflake's Parquet reader does not accept nanosecond precision
    df.to_parquet(buf, engine="pyarrow", index=False, coerce_timestamps="us", allow_truncated_timestamps=True)
    return buf.getvalue()


def write_to_lake(frames: Mapping[str, pd.DataFrame], run_date: date, settings: Settings) -> dict[str, str]:
    """Write each frame as <prefix>/<entity>/dt=<run_date>/<entity>.parquet. Re-running a day overwrites it."""
    locations: dict[str, str] = {}
    s3 = None
    if settings.load_target == "s3":
        import boto3

        s3 = boto3.client("s3")  # honours AWS_* env vars incl. AWS_ENDPOINT_URL for LocalStack

    for entity, df in frames.items():
        key = object_key(settings.s3_prefix, entity, run_date)
        body = to_parquet_bytes(df)
        if s3 is not None:
            s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=body, ServerSideEncryption="AES256")
            locations[entity] = f"s3://{settings.s3_bucket}/{key}"
        else:
            path = Path(settings.local_lake_dir) / key
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            locations[entity] = str(path)
        log.info("Landed %s rows -> %s", len(df), locations[entity])
    return locations
