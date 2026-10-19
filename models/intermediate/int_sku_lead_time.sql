-- Lead time mean and spread per SKU, in weeks, which is what the safety stock
-- formula consumes. SKUs with too few receipts get no statistics rather than a
-- confident number built on three observations.

select
    sku_id,
    count(*)                                    as receipts,
    avg(actual_lead_days) / 7.0                 as lead_weeks_mean,
    coalesce(stddev(actual_lead_days), 0) / 7.0 as lead_weeks_sd,
    avg(delay_days)                             as mean_delay_days,
    max(actual_lead_days) / 7.0                 as lead_weeks_max
from {{ ref('fct_purchase_orders') }}
group by 1
having count(*) >= {{ var('min_receipts_for_stats') }}
