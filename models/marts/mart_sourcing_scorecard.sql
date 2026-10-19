-- Country-level roll-up. Each penalty is kept as its own column so the
-- dashboard can show why a country scores where it does instead of just
-- reporting a number nobody can argue with.

{% set window = var('risk_window_days') %}

with window_start as (
    select max(order_date) - {{ window }} as from_date
    from {{ ref('fct_purchase_orders') }}
),

orders as (
    select
        country_iso3,
        count(*)                                     as orders,
        sum(line_value_usd)                          as spend_usd,
        avg(case when is_late then 0.0 else 1.0 end) as otif_rate,
        avg(delay_days)                              as mean_delay_days
    from {{ ref('fct_purchase_orders') }}
    where order_date >= (select w.from_date from window_start as w)
    group by 1
),

disruption as (
    select
        country_iso3,
        count(*)                                      as days_observed,
        sum(case when is_anomalous then 1 else 0 end) as anomalous_days
    from {{ ref('int_port_weather_anomaly') }}
    where obs_date >= current_date - {{ window }}
    group by 1
),

fx_now as (
    select
        currency,
        units_per_usd,
        return_zscore,
        rolling_vol_60d,
        row_number() over (partition by currency order by rate_date desc) as rn
    from {{ ref('int_fx_volatility') }}
),

fx_move as (
    select
        currency,
        100
        * (
            units_per_usd
            / nullif(lag(units_per_usd, 30) over (partition by currency order by rate_date), 0)
            - 1
        ) as pct_30d,
        row_number()
            over (partition by currency order by rate_date desc)
            as rn
    from {{ ref('stg_fx') }}
),

components as (
    select
        c.country_iso3,
        c.country_name,
        c.port,
        c.currency,
        c.lpi_score,
        o.orders,
        o.spend_usd,
        100 * o.otif_rate                                     as otif_pct,
        o.mean_delay_days,
        d.anomalous_days,
        d.days_observed,
        100.0 * d.anomalous_days / nullif(d.days_observed, 0) as disruption_rate_pct,
        m.pct_30d                                             as currency_move_30d,
        f.rolling_vol_60d * 100                               as currency_vol_pct,
        -- penalties, each on the same scale as the LPI points they subtract
        2.0 * d.anomalous_days / nullif(d.days_observed, 0)   as weather_penalty,
        0.02 * abs(coalesce(m.pct_30d, 0))                    as currency_penalty,
        0.04 * greatest(coalesce(o.mean_delay_days, 0), 0)    as delay_penalty
    from {{ ref('dim_country') }} as c
    left join orders as o on c.country_iso3 = o.country_iso3
    left join disruption as d on c.country_iso3 = d.country_iso3
    left join fx_now as f on c.currency = f.currency and f.rn = 1
    left join fx_move as m on c.currency = m.currency and m.rn = 1
)

select
    *,
    round(lpi_score - weather_penalty - currency_penalty - delay_penalty, 3) as sourcing_score
from components
order by sourcing_score desc
