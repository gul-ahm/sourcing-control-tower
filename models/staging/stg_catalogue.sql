select
    supplier_id,
    sku_id,
    contract_price_usd,
    moq_units,
    promised_lead_days
from {{ source('raw', 'supplier_catalogue') }}
