select
    po_id,
    supplier_id,
    sku_id,
    cast(order_date as date)                       as order_date,
    cast(promised_date as date)                    as promised_date,
    cast(received_date as date)                    as received_date,
    qty_units,
    unit_price_usd,
    line_value_usd,
    shipped_mode,
    expedite_cost_usd,
    date_diff('day', order_date, received_date)    as actual_lead_days,
    date_diff('day', order_date, promised_date)    as promised_lead_days,
    date_diff('day', promised_date, received_date) as delay_days
from {{ source('raw', 'purchase_orders') }}
