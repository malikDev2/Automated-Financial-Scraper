-- Upsert dimensions from staging (SCD Type 1: latest attributes overwrite; keys are stable).

MERGE INTO core.dim_products AS tgt
USING (
    SELECT ticker, company_name, sector, industry, exchange, currency
    FROM staging.stg_products
    QUALIFY ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY _loaded_at DESC) = 1
) AS src
ON tgt.ticker = src.ticker
WHEN MATCHED AND (
       tgt.company_name IS DISTINCT FROM src.company_name
    OR tgt.sector       IS DISTINCT FROM src.sector
    OR tgt.industry     IS DISTINCT FROM src.industry
    OR tgt.exchange     IS DISTINCT FROM src.exchange
    OR tgt.currency     IS DISTINCT FROM src.currency
) THEN UPDATE SET
    company_name = src.company_name,
    sector       = src.sector,
    industry     = src.industry,
    exchange     = src.exchange,
    currency     = src.currency,
    updated_at   = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (ticker, company_name, sector, industry, exchange, currency)
    VALUES (src.ticker, src.company_name, src.sector, src.industry, src.exchange, src.currency);

MERGE INTO core.dim_customers AS tgt
USING (
    SELECT customer_id, full_name, segment, country, signup_date
    FROM staging.stg_customers
    QUALIFY ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY _loaded_at DESC) = 1
) AS src
ON tgt.customer_id = src.customer_id
WHEN MATCHED AND (
       tgt.full_name   IS DISTINCT FROM src.full_name
    OR tgt.segment     IS DISTINCT FROM src.segment
    OR tgt.country     IS DISTINCT FROM src.country
    OR tgt.signup_date IS DISTINCT FROM src.signup_date
) THEN UPDATE SET
    full_name   = src.full_name,
    segment     = src.segment,
    country     = src.country,
    signup_date = src.signup_date,
    updated_at  = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (customer_id, full_name, segment, country, signup_date)
    VALUES (src.customer_id, src.full_name, src.segment, src.country, src.signup_date);
