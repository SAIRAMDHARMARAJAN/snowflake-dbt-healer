-- GOLD: the events worth attention — M4.5+, any PAGER alert, or a tsunami flag.
select
    e.event_i,
    e.event_time_utc,
    e.magnitude,
    case
        when e.magnitude >= 7 then 'Major (7+)'
        when e.magnitude >= 6 then 'Strong (6–6.9)'
        when e.magnitude >= 5 then 'Moderate (5–5.9)'
        else 'Light (4.5–4.9)'
    end                                   as magnitude_band,
    e.place,
    e.region,
    e.depth_km,
    e.alert_level,
    e.is_tsunami_flagged,
    e.felt_reports,
    e.significance,
    e.review_status,
    e.event_url
from {{ ref('stg_earthquakes') }} e
where e.event_type = 'earthquake'
  and (e.magnitude >= 4.5 or e.alert_level <> 'none' or e.is_tsunami_flagged)
