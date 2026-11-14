-- Per-run: reload staging from the day's Parquet partition in S3.
-- {run_date} is filled in by the pipeline (ISO date). FORCE = TRUE because staging is truncated each run
-- and the downstream MERGEs are idempotent, so re-processing a re-landed file is always safe.

TRUNCATE TABLE staging.stg_prices;
TRUNCATE TABLE staging.stg_products;
TRUNCATE TABLE staging.stg_customers;
TRUNCATE TABLE staging.stg_orders;

COPY INTO staging.stg_prices
FROM @staging.s3_raw_stage/prices/dt={run_date}/
FILE_FORMAT = (FORMAT_NAME = 'staging.parquet_ff')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
FORCE = TRUE
ON_ERROR = ABORT_STATEMENT;

COPY INTO staging.stg_products
FROM @staging.s3_raw_stage/products/dt={run_date}/
FILE_FORMAT = (FORMAT_NAME = 'staging.parquet_ff')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
FORCE = TRUE
ON_ERROR = ABORT_STATEMENT;

COPY INTO staging.stg_customers
FROM @staging.s3_raw_stage/customers/dt={run_date}/
FILE_FORMAT = (FORMAT_NAME = 'staging.parquet_ff')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
FORCE = TRUE
ON_ERROR = ABORT_STATEMENT;

COPY INTO staging.stg_orders
FROM @staging.s3_raw_stage/orders/dt={run_date}/
FILE_FORMAT = (FORMAT_NAME = 'staging.parquet_ff')
MATCH_BY_COLUMN_NAME = CASE_INSENSITIVE
FORCE = TRUE
ON_ERROR = ABORT_STATEMENT;
