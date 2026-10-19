{% snapshot supplier_snapshot %}
{{ config(
    target_schema='snapshots',
    unique_key='supplier_id',
    strategy='check',
    check_cols=['tier', 'quality_rating', 'payment_terms_days', 'incoterm']
) }}

select supplier_id, supplier_name, country_iso3, tier, quality_rating,
       payment_terms_days, incoterm
from {{ ref('stg_suppliers') }}

{% endsnapshot %}
