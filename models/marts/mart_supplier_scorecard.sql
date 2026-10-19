-- One row per supplier, on the measures a sourcing manager is actually judged
-- on: service level, how late they run when they slip, how much money sits
-- behind them, and how much of that is critical stock.

with quarter_start as (
    select max(order_date) - 90 as from_date
    from {{ ref('fct_purchase_orders') }}
),

perf as (
    select
        supplier_id,
        supplier_name,
        country_iso3,
        tier,
        count(*)                                                        as orders,
        sum(line_value_usd)                                             as spend_usd,
        avg(case when is_late then 0.0 else 1.0 end)                    as otif_rate,
        avg(delay_days)                                                 as mean_delay_days,
        quantile_cont(delay_days, 0.95)                                 as p95_delay_days,
        avg(storm_days)                                                 as mean_storm_days,
        sum(case when criticality = 'A' then line_value_usd else 0 end) as critical_spend_usd
    from {{ ref('fct_purchase_orders') }}
    group by 1, 2, 3, 4
),

-- Is the supplier drifting? Compare the most recent quarter with the rest.
trend as (
    select
        supplier_id,
        avg(case
            when order_date >= (select w.from_date from quarter_start as w)
                then delay_days
        end) as recent_delay,
        avg(case
            when order_date < (select w.from_date from quarter_start as w)
                then delay_days
        end) as prior_delay
    from {{ ref('fct_purchase_orders') }}
    group by 1
)

select
    p.supplier_id,
    p.supplier_name,
    p.country_iso3,
    p.tier,
    p.orders,
    round(p.spend_usd, 2)                    as spend_usd,
    round(p.critical_spend_usd, 2)           as critical_spend_usd,
    round(100 * p.otif_rate, 1)              as otif_pct,
    round(p.mean_delay_days, 1)              as mean_delay_days,
    round(p.p95_delay_days, 1)               as p95_delay_days,
    round(p.mean_storm_days, 2)              as mean_storm_days,
    round(t.recent_delay - t.prior_delay, 1) as delay_trend_days,
    case
        when t.recent_delay - t.prior_delay > 3 then 'deteriorating'
        when t.recent_delay - t.prior_delay < -3 then 'improving'
        else 'stable'
    end                                      as trend_flag
from perf as p
left join trend as t on p.supplier_id = t.supplier_id
