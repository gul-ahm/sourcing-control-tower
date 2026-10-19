select
    cast(rate_date as date) as rate_date,
    currency,
    units_per_usd
from {{ source('raw', 'fx') }}
where units_per_usd > 0
