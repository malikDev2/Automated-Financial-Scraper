-- Reporting layer: stable, denormalised views for Power BI and Excel.

CREATE OR REPLACE VIEW reporting.vw_orders_enriched AS
SELECT
    f.order_id,
    d.full_date        AS order_date,
    f.order_ts,
    c.customer_id,
    c.full_name,
    c.segment,
    c.country,
    p.ticker,
    p.company_name,
    p.sector,
    f.side,
    f.status,
    f.quantity,
    f.exec_price,
    f.gross_amount,
    f.fees,
    f.net_amount
FROM core.fact_orders f
JOIN core.dim_customers c ON c.customer_key = f.customer_key
JOIN core.dim_products  p ON p.product_key  = f.product_key
JOIN core.dim_date      d ON d.date_key     = f.date_key;

CREATE OR REPLACE VIEW reporting.vw_daily_order_summary AS
SELECT
    d.full_date                                                          AS order_date,
    p.ticker,
    p.company_name,
    p.sector,
    COUNT(*)                                                             AS total_orders,
    COUNT_IF(f.status = 'FILLED')                                        AS filled_orders,
    COUNT_IF(f.status = 'CANCELLED')                                     AS cancelled_orders,
    COUNT_IF(f.status = 'REJECTED')                                      AS rejected_orders,
    SUM(IFF(f.side = 'BUY'  AND f.status = 'FILLED', f.gross_amount, 0)) AS buy_notional,
    SUM(IFF(f.side = 'SELL' AND f.status = 'FILLED', f.gross_amount, 0)) AS sell_notional,
    SUM(f.fees)                                                          AS total_fees
FROM core.fact_orders f
JOIN core.dim_date     d ON d.date_key    = f.date_key
JOIN core.dim_products p ON p.product_key = f.product_key
GROUP BY d.full_date, p.ticker, p.company_name, p.sector;

CREATE OR REPLACE VIEW reporting.vw_ticker_performance AS
SELECT
    d.full_date        AS trade_date,
    p.ticker,
    p.company_name,
    p.sector,
    fp.open_price,
    fp.high_price,
    fp.low_price,
    fp.close_price,
    fp.volume,
    fp.price_change_pct
FROM core.fact_daily_prices fp
JOIN core.dim_date     d ON d.date_key    = fp.date_key
JOIN core.dim_products p ON p.product_key = fp.product_key;
