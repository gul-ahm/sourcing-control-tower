-- A fixed millimetre threshold treats Hamburg and Nhava Sheva as the same port.
-- Severity is scored against each port's own distribution instead, so "extreme"
-- means extreme for that port.

with ranked as (
    select
        country_iso3,
        port,
        obs_date,
        precip_mm,
        wind_kmh,
        percent_rank() over (partition by port order by precip_mm) as precip_pctile,
        percent_rank() over (partition by port order by wind_kmh)  as wind_pctile
    from {{ ref('stg_port_weather') }}
)

select
    *,
    greatest(precip_pctile, wind_pctile)                                as severity_pctile,
    greatest(precip_pctile, wind_pctile) >= {{ var('anomaly_pctile') }} as is_anomalous
from ranked
