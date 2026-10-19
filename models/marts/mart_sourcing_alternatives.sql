-- For every SKU currently bought from a supplier, what else could supply it,
-- and what would switching cost or save on price, service and risk.
-- This is the model behind the switch view: without it the dashboard can only
-- report problems, not propose moves.

with current as (
    select
        c.supplier_id,
        c.sku_id,
        c.contract_price_usd,
        c.promised_lead_days,
        s.supplier_name,
        s.country_iso3,
        sc.otif_pct,
        sc.mean_delay_days
    from {{ ref('stg_catalogue') }} as c
    inner join {{ ref('stg_suppliers') }} as s on c.supplier_id = s.supplier_id
    left join {{ ref('mart_supplier_scorecard') }} as sc on c.supplier_id = sc.supplier_id
),

spend as (
    select
        supplier_id,
        sku_id,
        sum(line_value_usd) as sku_spend_usd,
        count(*)            as orders
    from {{ ref('fct_purchase_orders') }}
    group by 1, 2
),

paired as (
    select
        cur.supplier_id                                                as from_supplier_id,
        cur.supplier_name                                              as from_supplier,
        cur.country_iso3                                               as from_country,
        alt.supplier_id                                                as to_supplier_id,
        alt.supplier_name                                              as to_supplier,
        alt.country_iso3                                               as to_country,
        cur.sku_id,
        k.category,
        k.criticality,
        sp.sku_spend_usd,
        sp.orders,
        cur.contract_price_usd                                         as from_price_usd,
        alt.contract_price_usd                                         as to_price_usd,
        alt.contract_price_usd / nullif(cur.contract_price_usd, 0) - 1 as price_change,
        round(alt.otif_pct - cur.otif_pct, 1)                          as otif_delta_pts,
        round(cur.mean_delay_days - alt.mean_delay_days, 1)            as delay_saved_days,
        alt.promised_lead_days - cur.promised_lead_days                as lead_time_delta_days
    from current as cur
    inner join current as alt
        on
            cur.sku_id = alt.sku_id
            and cur.supplier_id <> alt.supplier_id
    inner join {{ ref('stg_skus') }} as k on cur.sku_id = k.sku_id
    inner join spend as sp on cur.supplier_id = sp.supplier_id and cur.sku_id = sp.sku_id
)

select
    * exclude (price_change),
    round(100 * price_change, 1)           as price_delta_pct,
    -- Annualised price impact if the whole SKU line moved across.
    round(sku_spend_usd * price_change, 2) as price_impact_usd
from paired
