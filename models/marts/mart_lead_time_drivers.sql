-- What actually explains a late delivery? Compares mean delay across storm
-- exposure, which gives the per-storm-day cost used in the attribution view.
-- Nothing here is assumed: the numbers come out of the order book.

with by_storms as (
    select
        storm_days,
        count(*)            as orders,
        avg(delay_days)     as mean_delay_days,
        sum(line_value_usd) as spend_usd
    from {{ ref('fct_purchase_orders') }}
    group by 1
),

baseline as (
    select mean_delay_days from by_storms
    where storm_days = 0
),

-- Slope of delay against storm days, weighted by order count.
regression as (
    select
        regr_slope(mean_delay_days, storm_days) as days_lost_per_storm_day,
        regr_r2(mean_delay_days, storm_days)    as r2
    from by_storms
    where orders >= 30
)

select
    b.storm_days,
    b.orders,
    round(b.mean_delay_days, 2)                        as mean_delay_days,
    round(b.mean_delay_days - base.mean_delay_days, 2) as delay_vs_clean_transit,
    b.spend_usd,
    round(r.days_lost_per_storm_day, 2)                as days_lost_per_storm_day,
    round(r.r2, 3)                                     as model_r2
from by_storms as b
cross join baseline as base
cross join regression as r
order by b.storm_days
