-- The number a sourcing director asks for: how much money is sitting behind
-- lanes that are running late, and what is driving it.
--
-- "Exposed" is deliberately narrow. Nearly every long-haul order touches some
-- bad weather, so counting any storm day flags ~88% of spend and tells nobody
-- anything. Exposure here means an order that slipped past tolerance (>7 days
-- late) AND had an anomalous port day in transit — late, with a cause.

{% set window = var('risk_window_days') %}

with window_start as (
    select max(order_date) - {{ window }} as from_date
    from {{ ref('fct_purchase_orders') }}
),

recent as (
    select *
    from {{ ref('fct_purchase_orders') }}
    where order_date >= (select w.from_date from window_start as w)
),

cost_per_storm_day as (
    select max(days_lost_per_storm_day) as days_per_storm from {{ ref('mart_lead_time_drivers') }}
),

lane as (
    select
        r.country_iso3,
        r.category,
        count(*)              as orders,
        sum(r.line_value_usd) as spend_usd,
        sum(case
            when r.storm_days > 0 and r.delay_days > {{ var('late_tolerance_days') }}
                then r.line_value_usd
            else 0
        end)                  as exposed_spend_usd,
        sum(case
            when
                r.criticality = 'A' and r.storm_days > 0
                and r.delay_days > {{ var('late_tolerance_days') }}
                then r.line_value_usd
            else 0
        end)                  as exposed_critical_usd,
        sum(r.storm_days)     as storm_days,
        avg(r.delay_days)     as mean_delay_days
    from recent as r
    group by 1, 2
)

select
    l.country_iso3,
    c.port,
    l.category,
    l.orders,
    round(l.spend_usd, 2)                                        as spend_usd,
    round(l.exposed_spend_usd, 2)                                as exposed_spend_usd,
    round(l.exposed_critical_usd, 2)                             as exposed_critical_usd,
    round(100 * l.exposed_spend_usd / nullif(l.spend_usd, 0), 1) as exposed_pct,
    l.storm_days,
    round(l.mean_delay_days, 1)                                  as mean_delay_days,
    round(l.storm_days * d.days_per_storm, 1)                    as est_days_lost
from lane as l
inner join {{ ref('dim_country') }} as c on l.country_iso3 = c.country_iso3
cross join cost_per_storm_day as d
order by exposed_spend_usd desc
