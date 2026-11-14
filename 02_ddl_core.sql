-- Core layer: dimensional star schema.
--   dim_customers --\
--   dim_products  ---+--> fact_orders          (grain: one row per order)
--   dim_date      --/ \
--   dim_products  ---+--> fact_daily_prices    (grain: one row per ticker per trading day)
-- Surrogate keys are Snowflake IDENTITY columns; business keys carry UNIQUE constraints.
-- (Snowflake records but does not enforce constraints - integrity is verified by the post-load checks.)

CREATE TABLE IF NOT EXISTS core.dim_date (
    date_key          NUMBER(8, 0)  NOT NULL,
    full_date         DATE          NOT NULL,
    year_num          NUMBER(4, 0),
    quarter_num       NUMBER(1, 0),
    month_num         NUMBER(2, 0),
    month_name        VARCHAR(10),
    day_of_week_num   NUMBER(1, 0),
    day_name          VARCHAR(10),
    is_weekend        BOOLEAN,
    PRIMARY KEY (date_key)
);

INSERT INTO core.dim_date
SELECT
    TO_NUMBER(TO_CHAR(d, 'YYYYMMDD')),
    d,
    YEAR(d),
    QUARTER(d),
    MONTH(d),
    MONTHNAME(d),
    DAYOFWEEKISO(d),
    DAYNAME(d),
    IFF(DAYOFWEEKISO(d) >= 6, TRUE, FALSE)
FROM (
    SELECT DATEADD(DAY, SEQ4(), '2022-01-01'::DATE) AS d
    FROM TABLE(GENERATOR(ROWCOUNT => 5479))
)
WHERE NOT EXISTS (SELECT 1 FROM core.dim_date);

CREATE TABLE IF NOT EXISTS core.dim_customers (
    customer_key   NUMBER(38, 0)  IDENTITY(1, 1) NOT NULL,
    customer_id    VARCHAR(32)    NOT NULL,
    full_name      VARCHAR,
    segment        VARCHAR(16),
    country        VARCHAR(2),
    signup_date    DATE,
    created_at     TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    updated_at     TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (customer_key),
    UNIQUE (customer_id)
);

CREATE TABLE IF NOT EXISTS core.dim_products (
    product_key    NUMBER(38, 0)  IDENTITY(1, 1) NOT NULL,
    ticker         VARCHAR(16)    NOT NULL,
    company_name   VARCHAR,
    sector         VARCHAR,
    industry       VARCHAR,
    exchange       VARCHAR,
    currency       VARCHAR(8),
    created_at     TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    updated_at     TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (product_key),
    UNIQUE (ticker)
);

CREATE TABLE IF NOT EXISTS core.fact_orders (
    order_id       VARCHAR(32)    NOT NULL,
    customer_key   NUMBER(38, 0)  NOT NULL,
    product_key    NUMBER(38, 0)  NOT NULL,
    date_key       NUMBER(8, 0)   NOT NULL,
    order_ts       TIMESTAMP_NTZ  NOT NULL,
    side           VARCHAR(4)     NOT NULL,
    status         VARCHAR(10)    NOT NULL,
    quantity       NUMBER(18, 0)  NOT NULL,
    exec_price     NUMBER(18, 4)  NOT NULL,
    gross_amount   NUMBER(18, 4)  NOT NULL,
    fees           NUMBER(18, 4)  NOT NULL,
    net_amount     NUMBER(18, 4)  NOT NULL,
    batch_date     DATE           NOT NULL,
    loaded_at      TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (order_id),
    FOREIGN KEY (customer_key) REFERENCES core.dim_customers (customer_key),
    FOREIGN KEY (product_key)  REFERENCES core.dim_products (product_key),
    FOREIGN KEY (date_key)     REFERENCES core.dim_date (date_key)
)
CLUSTER BY (date_key);

CREATE TABLE IF NOT EXISTS core.fact_daily_prices (
    product_key        NUMBER(38, 0)  NOT NULL,
    date_key           NUMBER(8, 0)   NOT NULL,
    open_price         NUMBER(18, 4),
    high_price         NUMBER(18, 4),
    low_price          NUMBER(18, 4),
    close_price        NUMBER(18, 4),
    adj_close_price    NUMBER(18, 4),
    volume             NUMBER(38, 0),
    price_change_pct   NUMBER(18, 4),
    batch_date         DATE           NOT NULL,
    loaded_at          TIMESTAMP_NTZ  DEFAULT CURRENT_TIMESTAMP(),
    PRIMARY KEY (product_key, date_key),
    FOREIGN KEY (product_key) REFERENCES core.dim_products (product_key),
    FOREIGN KEY (date_key)    REFERENCES core.dim_date (date_key)
);

-- Pipeline run history (written by the ETL, one row per run attempt)
CREATE TABLE IF NOT EXISTS ops.etl_run_audit (
    run_id           VARCHAR        NOT NULL,
    run_date         DATE           NOT NULL,
    status           VARCHAR(10)    NOT NULL,
    rows_prices      NUMBER,
    rows_products    NUMBER,
    rows_customers   NUMBER,
    rows_orders      NUMBER,
    started_at       TIMESTAMP_NTZ,
    finished_at      TIMESTAMP_NTZ,
    error_message    VARCHAR
);
