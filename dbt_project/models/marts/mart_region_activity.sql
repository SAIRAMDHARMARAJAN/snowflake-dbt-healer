-- GOLD: one row per region — how active it is now and its strongest recent quake.
select
    e.region,
    count(*)                                                        as earthquakes,
    count_if(e.event_time_utc >= dateadd('hour', -24, sysdate()))   as earthquakes_last_24h,
    max(e.magnitude)                                                as max_magnitude,
    max_by(e.place, e.magnitude)                                    as strongest_place,
    max_by(e.event_time_utc, e.magnitude)                           as strongest_at_utc,
    round(avg(e.magnitude), 2)                                      as avg_magnitude,
    round(avg(e.depth_km), 1)                                       as avg_depth_km,
    max(e.event_time_utc)                                           as latest_event_utc,
    round(100 * count_if(e.review_status = 'reviewed') / count(*), 1) as reviewed_pct
from {{ ref('stg_earthquake') }} e
where e.event_type = 'earthquake'
  and e.magnitude is not null
group by 1
