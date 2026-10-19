-- Kept as the published disruption fact, now scored against each port's own
-- distribution rather than a fixed millimetre cut-off.
select
    country_iso3,
    port,
    obs_date,
    precip_mm,
    wind_kmh,
    round(severity_pctile, 4) as severity_pctile,
    is_anomalous              as is_disrupted
from {{ ref('int_port_weather_anomaly') }}
