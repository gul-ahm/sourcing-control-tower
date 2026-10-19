-- The list a sourcing director actually acts on: critical items that depend on
-- one supplier, sitting behind a port that keeps closing.
--
-- Spend alone does not find these. A $40k SKU with one source at a disrupted
-- port is a bigger problem than a $4M SKU with four qualified alternatives.

with sources as (
    select
        sku_id,
        count(distinct supplier_id) as qualified_suppliers
    from {{ ref('stg_catalogue') }}
    group by 1
),

buying as (
    select
        sku_id,
        count(distinct supplier_id) as suppliers_used,
        min(supplier_id)            as primary_supplier_id,
        sum(line_value_usd)         as spend_usd,
        avg(delay_days)             as mean_delay_days,
        avg(storm_days)             as mean_storm_days,
        sum(expedite_cost_usd)      as expedite_cost_usd
    from {{ ref('fct_purchase_orders') }}
    group by 1
),

port_risk as (
    select
        country_iso3,
        100.0 * sum(case when is_anomalous then 1 else 0 end) / count(*) as disruption_rate_pct
    from {{ ref('int_port_weather_anomaly') }}
    group by 1
)

select
    ss.sku_id,
    ss.sku_name,
    ss.category,
    ss.criticality,
    s.supplier_name                  as primary_supplier,
    s.country_iso3,
    c.port,
    src.qualified_suppliers,
    b.suppliers_used,
    round(b.spend_usd, 2)            as spend_usd,
    round(b.mean_delay_days, 1)      as mean_delay_days,
    round(pr.disruption_rate_pct, 1) as port_disruption_rate_pct,
    ss.safety_stock_units,
    ss.safety_stock_value_usd,
    round(b.expedite_cost_usd, 2)    as expedite_cost_usd,
    -- Severity, not a flag: concentration x criticality x port risk.
    round(
        (case when src.qualified_suppliers = 1 then 1.0 else 1.0 / src.qualified_suppliers end)
        * (case ss.criticality when 'A' then 3.0 when 'B' then 1.5 else 1.0 end)
        * (1 + pr.disruption_rate_pct / 10.0), 2
    )                                as concentration_risk_score
from {{ ref('mart_safety_stock') }} as ss
inner join buying as b on ss.sku_id = b.sku_id
inner join sources as src on ss.sku_id = src.sku_id
inner join {{ ref('stg_suppliers') }} as s on b.primary_supplier_id = s.supplier_id
inner join {{ ref('dim_country') }} as c on s.country_iso3 = c.country_iso3
left join port_risk as pr on s.country_iso3 = pr.country_iso3
order by concentration_risk_score desc, spend_usd desc
