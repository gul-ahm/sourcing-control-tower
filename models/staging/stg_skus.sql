select
    sku_id,
    sku_name,
    category,
    criticality,
    unit_cost_usd,
    shelf_life_days
from {{ source('raw', 'skus') }}
