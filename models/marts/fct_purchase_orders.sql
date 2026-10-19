{{ config(
    materialized='incremental',
    unique_key='po_id',
    incremental_strategy='delete+insert',
    on_schema_change='fail'
) }}

select
    e.po_id,
    e.supplier_id,
    e.supplier_name,
    e.country_iso3,
    e.tier,
    e.sku_id,
    k.category,
    k.criticality,
    e.order_date,
    e.promised_date,
    e.received_date,
    e.qty_units,
    e.unit_price_usd,
    e.line_value_usd,
    e.shipped_mode,
    e.expedite_cost_usd,
    e.promised_lead_days,
    e.actual_lead_days,
    e.delay_days,
    e.delay_bucket,
    e.is_late,
    e.storm_days,
    e.worst_severity
from {{ ref('int_po_exposure') }} as e
inner join {{ ref('stg_skus') }} as k on e.sku_id = k.sku_id

{% if is_incremental() %}
-- Reload a trailing window rather than the full book: receipts and dates get
-- corrected after the fact, so the last 60 days are never settled.
    where e.order_date >= (select max(prev.order_date) - 60 from {{ this }} as prev)
{% endif %}
