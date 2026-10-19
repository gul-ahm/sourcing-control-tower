-- Join every order back to the weather at its origin port over the days it was
-- meant to be in transit. Nothing upstream records this: the storm count is
-- derived here, which is what lets the lead-time analysis stand on its own.

with orders as (
    select
        po.*,
        s.country_iso3,
        s.supplier_name,
        s.tier
    from {{ ref('stg_purchase_orders') }} as po
    inner join {{ ref('stg_suppliers') }} as s on po.supplier_id = s.supplier_id
),

storms as (
    select
        o.po_id,
        count(*) filter (where w.is_anomalous) as storm_days,
        coalesce(max(w.severity_pctile), 0)    as worst_severity
    from orders as o
    left join {{ ref('int_port_weather_anomaly') }} as w
        on
            o.country_iso3 = w.country_iso3
            and w.obs_date between o.order_date and o.promised_date
    group by 1
)

select
    o.*,
    coalesce(s.storm_days, 0) as storm_days,
    s.worst_severity,
    o.delay_days > 0          as is_late,
    case
        when o.delay_days <= 0 then 'on time'
        when o.delay_days <= 7 then '1-7 days'
        when o.delay_days <= 21 then '8-21 days'
        else 'over 21 days'
    end                       as delay_bucket
from orders as o
left join storms as s on o.po_id = s.po_id
