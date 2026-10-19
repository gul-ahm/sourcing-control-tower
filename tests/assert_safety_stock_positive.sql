-- A buffer of zero or less means the formula took a null somewhere.
select
    sku_id,
    safety_stock_units
from {{ ref('mart_safety_stock') }}
where safety_stock_units <= 0 or safety_stock_value_usd is null
