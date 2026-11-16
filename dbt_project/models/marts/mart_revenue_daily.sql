select
    o.order_date,
    coalesce(c.region, 'UNKNOWN')           as region,
    count(distinct o.order_id)              as total_orders,
    count(distinct o.customer_id)           as unique_customers,
    sum(o.amount)                           as total_revenue,
    round(avg(o.amount), 2)                 as avg_order_value
from {{ ref('stg_orders') }} o
left join {{ ref('stg_customers') }} c
    on c.customer_id = o.customer_id
where o.status = 'completed'
group by 1, 2
