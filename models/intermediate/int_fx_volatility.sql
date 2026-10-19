-- Daily moves mean nothing on their own: a 1% day is noise for BRL and a
-- shock for EUR. Scored as a z-score against each currency's own 60-day window.

with daily as (
    select
        rate_date,
        currency,
        units_per_usd,
        units_per_usd / lag(units_per_usd) over (partition by currency order by rate_date)
        - 1 as daily_return
    from {{ ref('stg_fx') }}
),

scored as (
    select
        *,
        avg(daily_return) over w    as mean_return,
        stddev(daily_return) over w as vol
    from daily
    window w as (
        partition by currency order by rate_date
        rows between 60 preceding and 1 preceding
    )
)

select
    rate_date,
    currency,
    units_per_usd,
    daily_return,
    vol as rolling_vol_60d,
    case
        when vol is null or vol = 0 then null
        else (daily_return - mean_return) / vol
    end as return_zscore
from scored
