-- Staging layer: transient (no fail-safe cost), truncated and reloaded on every run.
-- Column names match the Parquet files exactly so COPY can use MATCH_BY_COLUMN_NAME.

CREATE TRANSIENT TABLE IF NOT EXISTS staging.stg_prices (
    ticker             VARCHAR(16)    NOT NULL,
    trade_date         DATE           NOT NULL,
    open_price         NUMBER(18, 4),
    high_price         NUMBER(18, 4),
    low_price          NUMBER(18, 4),
    close_price        NUMBER(18, 4),
    adj_close_price    NUMBER(18, 4),
    volume             NUMBER(38, 0),
    price_change_pct   NUMBER(18, 4),
    batch_date         DATE           NOT NULL,
    _loaded_at         TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()
);

CREATE TRANSIENT TABLE IF NOT EXISTS staging.stg_products (
    ticker             VARCHAR(16)    NOT NULL,
    company_name       VARCHAR,
    sector             VARCHAR,
    industry           VARCHAR,
    exchange           VARCHAR,
    currency           VARCHAR(8),
    batch_date         DATE           NOT NULL,
    _loaded_at         TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()
);

CREATE TRANSIENT TABLE IF NOT EXISTS staging.stg_customers (
    customer_id        VARCHAR(32)    NOT NULL,
    full_name          VARCHAR,
    segment            VARCHAR(16),
    country            VARCHAR(2),
    signup_date        DATE,
    batch_date         DATE           NOT NULL,
    _loaded_at         TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()
);

CREATE TRANSIENT TABLE IF NOT EXISTS staging.stg_orders (
    order_id           VARCHAR(32)    NOT NULL,
    customer_id        VARCHAR(32)    NOT NULL,
    ticker             VARCHAR(16)    NOT NULL,
    side               VARCHAR(4)     NOT NULL,
    status             VARCHAR(10)    NOT NULL,
    quantity           NUMBER(18, 0)  NOT NULL,
    exec_price         NUMBER(18, 4)  NOT NULL,
    gross_amount       NUMBER(18, 4),
    fees               NUMBER(18, 4),
    net_amount         NUMBER(18, 4),
    order_ts           TIMESTAMP_NTZ  NOT NULL,
    order_date         DATE           NOT NULL,
    batch_date         DATE           NOT NULL,
    _loaded_at         TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP()
);
