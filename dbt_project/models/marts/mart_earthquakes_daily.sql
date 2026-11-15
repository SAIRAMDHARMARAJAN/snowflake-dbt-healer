select
    e.event_date_utc,
    e.region,
    count(*)                                      as earthquakes,
    round(avg(e.magnitude), 2)                    as avg_magnitude,
    max(e.magnitude)                              as max_magnitude,
    count_if(e.magnitude >= 4.5)                  as strong_earthquakes,
    round(avg(e.depth_km), 1)                     as avg_depth_km,
    sum(e.felt_reports)                           as felt_reports,
    count_if(e.is_tsunami_flagged)                as tsunami_flags
from {{ ref('stg_earthquakes') }} e
where e.event_type = 'earthquake'
  and e.magnitude is not null
group by 1, 2
