-- What port disruption costs, in money rather than in days.
--
-- Two components, both observable in the book:
--   expedite  - air freight actually paid to rescue critical lines
--   carrying  - the extra safety stock held only because lead times are
--               unreliable, at an annual carrying rate
--
-- Delay days alone are not a cost. These are.

{% set carrying_rate = var('inventory_carrying_rate') %}

with by_country as (
    select
        country_iso3,
        count(*)                                              as orders,
        sum(line_value_usd)                                   as spend_usd,
        sum(expedite_cost_usd)                                as expedite_cost_usd,
        sum(case when shipped_mode = 'Air' then 1 else 0 end) as air_shipments,
        sum(storm_days)                                       as storm_days,
        avg(delay_days)                                       as mean_delay_days
    from {{ ref('fct_purchase_orders') }}
    group by 1
),

buffer_cost as (
    select
        s.country_iso3,
        sum(ss.safety_stock_value_usd * ss.pct_buffer_from_lead_time / 100.0)
            as lead_time_buffer_usd
    from {{ ref('mart_safety_stock') }} as ss
    inner join {{ ref('stg_catalogue') }} as c on ss.sku_id = c.sku_id
    inner join {{ ref('stg_suppliers') }} as s on c.supplier_id = s.supplier_id
    group by 1
)

select
    b.country_iso3,
    d.country_name,
    d.port,
    b.orders,
    round(b.spend_usd, 2)                          as spend_usd,
    b.air_shipments,
    round(b.expedite_cost_usd, 2)                  as expedite_cost_usd,
    round(coalesce(bc.lead_time_buffer_usd, 0), 2) as lead_time_buffer_usd,
    round(coalesce(bc.lead_time_buffer_usd, 0) * {{ carrying_rate }}, 2)
        as annual_carrying_cost_usd,
    round(
        b.expedite_cost_usd
        + coalesce(bc.lead_time_buffer_usd, 0) * {{ carrying_rate }}, 2
    )                                              as total_disruption_cost_usd,
    round(100 * (
        b.expedite_cost_usd
        + coalesce(bc.lead_time_buffer_usd, 0) * {{ carrying_rate }}
    )
    / nullif(b.spend_usd, 0), 2)                   as cost_pct_of_spend,
    b.storm_days,
    round(b.mean_delay_days, 1)                    as mean_delay_days
from by_country as b
inner join {{ ref('dim_country') }} as d on b.country_iso3 = d.country_iso3
left join buffer_cost as bc on b.country_iso3 = bc.country_iso3
order by total_disruption_cost_usd desc
