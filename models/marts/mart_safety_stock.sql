-- Safety stock sized against both demand and lead-time variability:
--
--   SS = Z * sqrt( L * sd_demand^2 + demand^2 * sd_lead^2 )
--
-- The second term is the one most buffers miss. A supplier whose lead time
-- swings by two weeks drives more stock than one with volatile demand but a
-- lead time you can set a watch by.
--
-- Z comes from the item's criticality, which is where ABC classification stops
-- being a label: an A item is held to a 99% service level, a C item to 90%.

with demand as (
    select
        sku_id,
        avg(units_consumed)                 as weekly_demand,
        coalesce(stddev(units_consumed), 0) as weekly_demand_sd,
        count(*)                            as weeks_observed
    from {{ ref('stg_demand') }}
    group by 1
),

z as (
    select 'A' as criticality, 0.99 as service_level, 2.326 as z
    union all
    select 'B', 0.95, 1.645
    union all
    select 'C', 0.90, 1.282
)

select
    k.sku_id,
    k.sku_name,
    k.category,
    k.criticality,
    k.unit_cost_usd,
    z.service_level,
    round(d.weekly_demand, 1)                      as weekly_demand,
    round(d.weekly_demand_sd, 1)                   as weekly_demand_sd,
    round(lt.lead_weeks_mean, 2)                   as lead_weeks_mean,
    round(lt.lead_weeks_sd, 2)                     as lead_weeks_sd,
    lt.receipts,
    round(d.weekly_demand * lt.lead_weeks_mean, 0) as cycle_stock_units,
    round(
        z.z * sqrt(
            lt.lead_weeks_mean * pow(d.weekly_demand_sd, 2)
            + pow(d.weekly_demand, 2) * pow(lt.lead_weeks_sd, 2)
        ), 0
    )                                              as safety_stock_units,
    round(
        z.z * sqrt(
            lt.lead_weeks_mean * pow(d.weekly_demand_sd, 2)
            + pow(d.weekly_demand, 2) * pow(lt.lead_weeks_sd, 2)
        ) * k.unit_cost_usd, 2
    )                                              as safety_stock_value_usd,
    -- How much of the buffer exists only because lead time is unreliable.
    round(
        100 * pow(d.weekly_demand, 2) * pow(lt.lead_weeks_sd, 2)
        / nullif(
            lt.lead_weeks_mean * pow(d.weekly_demand_sd, 2)
            + pow(d.weekly_demand, 2) * pow(lt.lead_weeks_sd, 2), 0
        ), 1
    )                                              as pct_buffer_from_lead_time
from {{ ref('stg_skus') }} as k
inner join demand as d on k.sku_id = d.sku_id
inner join {{ ref('int_sku_lead_time') }} as lt on k.sku_id = lt.sku_id
inner join z on k.criticality = z.criticality
