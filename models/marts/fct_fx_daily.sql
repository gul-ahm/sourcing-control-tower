with ranked as (
    select
        rate_date,
        currency,
        units_per_usd,
        first_value(units_per_usd) over (
            partition by currency order by rate_date
        ) as first_rate,
        lag(units_per_usd, 30) over (
            partition by currency order by rate_date
        ) as rate_30d_ago
    from {{ ref('stg_fx') }}
)

select
    rate_date,
    currency,
    units_per_usd,
    round(100 * (units_per_usd / first_rate - 1), 2)   as pct_vs_window_start,
    round(100 * (units_per_usd / rate_30d_ago - 1), 2) as pct_vs_30d_ago
from ranked
