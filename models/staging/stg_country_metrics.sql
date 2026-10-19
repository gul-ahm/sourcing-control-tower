-- World Bank returns one row per indicator; pivot to one row per country-year.
select
    country_iso3,
    country_name,
    year,
    max(case when metric = 'lpi_score' then value end)       as lpi_score,
    max(case when metric = 'gdp_usd' then value end)         as gdp_usd,
    max(case when metric = 'imports_pct_gdp' then value end) as imports_pct_gdp
from {{ source('raw', 'worldbank') }}
where country_iso3 is not null
group by 1, 2, 3
