select
    country_iso3,
    port,
    cast(obs_date as date) as obs_date,
    coalesce(precip_mm, 0) as precip_mm,
    coalesce(wind_kmh, 0)  as wind_kmh
from {{ source('raw', 'weather') }}
