select
    sku_id,
    cast(week_start as date) as week_start,
    units_consumed
from {{ source('raw', 'demand') }}
