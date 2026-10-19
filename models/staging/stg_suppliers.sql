select
    supplier_id,
    supplier_name,
    country_iso3,
    tier,
    cast(onboarded_on as date) as onboarded_on,
    quality_rating,
    payment_terms_days,
    incoterm
from {{ source('raw', 'suppliers') }}
