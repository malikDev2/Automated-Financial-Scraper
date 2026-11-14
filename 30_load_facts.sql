-- Load facts by joining staging to dimensions for surrogate keys.
-- MERGE on the business key makes every run idempotent (re-running a day updates, never duplicates).

MERGE INTO core.fact_orders AS tgt
USING (
    SELECT
        o.order_id,
        c.customer_key,
        p.product_key,
        TO_NUMBER(TO_CHAR(o.order_date, 'YYYYMMDD')) AS date_key,
        o.order_ts,
        o.side,
        o.status,
        o.quantity,
        o.exec_price,
        o.gross_amount,
        o.fees,
        o.net_amount,
        o.batch_date
    FROM staging.stg_orders o
    JOIN core.dim_customers c ON c.customer_id = o.customer_id
    JOIN core.dim_products  p ON p.ticker      = o.ticker
    QUALIFY ROW_NUMBER() OVER (PARTITION BY o.order_id ORDER BY o._loaded_at DESC) = 1
) AS src
ON tgt.order_id = src.order_id
WHEN MATCHED THEN UPDATE SET
    customer_key = src.customer_key,
    product_key  = src.product_key,
    date_key     = src.date_key,
    order_ts     = src.order_ts,
    side         = src.side,
    status       = src.status,
    quantity     = src.quantity,
    exec_price   = src.exec_price,
    gross_amount = src.gross_amount,
    fees         = src.fees,
    net_amount   = src.net_amount,
    batch_date   = src.batch_date,
    loaded_at    = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
    order_id, customer_key, product_key, date_key, order_ts, side, status,
    quantity, exec_price, gross_amount, fees, net_amount, batch_date
) VALUES (
    src.order_id, src.customer_key, src.product_key, src.date_key, src.order_ts, src.side, src.status,
    src.quantity, src.exec_price, src.gross_amount, src.fees, src.net_amount, src.batch_date
);

MERGE INTO core.fact_daily_prices AS tgt
USING (
    SELECT
        p.product_key,
        TO_NUMBER(TO_CHAR(s.trade_date, 'YYYYMMDD')) AS date_key,
        s.open_price,
        s.high_price,
        s.low_price,
        s.close_price,
        s.adj_close_price,
        s.volume,
        s.price_change_pct,
        s.batch_date
    FROM staging.stg_prices s
    JOIN core.dim_products p ON p.ticker = s.ticker
    QUALIFY ROW_NUMBER() OVER (PARTITION BY s.ticker, s.trade_date ORDER BY s._loaded_at DESC) = 1
) AS src
ON tgt.product_key = src.product_key AND tgt.date_key = src.date_key
WHEN MATCHED THEN UPDATE SET
    open_price       = src.open_price,
    high_price       = src.high_price,
    low_price        = src.low_price,
    close_price      = src.close_price,
    adj_close_price  = src.adj_close_price,
    volume           = src.volume,
    price_change_pct = src.price_change_pct,
    batch_date       = src.batch_date,
    loaded_at        = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
    product_key, date_key, open_price, high_price, low_price, close_price,
    adj_close_price, volume, price_change_pct, batch_date
) VALUES (
    src.product_key, src.date_key, src.open_price, src.high_price, src.low_price, src.close_price,
    src.adj_close_price, src.volume, src.price_change_pct, src.batch_date
);
