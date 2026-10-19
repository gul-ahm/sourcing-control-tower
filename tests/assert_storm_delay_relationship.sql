-- The whole analysis rests on storms extending lead times. If that slope ever
-- goes flat or negative the marts are reporting a relationship that is not
-- there, and every downstream cost number is noise. Fail loudly.

select
    days_lost_per_storm_day,
    model_r2
from {{ ref('mart_lead_time_drivers') }}
where days_lost_per_storm_day <= 0 or model_r2 < 0.5
