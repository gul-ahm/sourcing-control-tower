with latest as (
    select
        country_iso3,
        country_name,
        lpi_score,
        gdp_usd,
        imports_pct_gdp,
        row_number() over (partition by country_iso3 order by year desc) as rn
    from {{ ref('stg_country_metrics') }}
    where lpi_score is not null
)

select
    c.country_iso3,
    l.country_name,
    c.currency,
    c.port,
    c.lat,
    c.lon,
    l.lpi_score,
    l.gdp_usd,
    l.imports_pct_gdp
from {{ source('raw', 'countries') }} as c
left join latest as l
    on c.country_iso3 = l.country_iso3 and l.rn = 1
