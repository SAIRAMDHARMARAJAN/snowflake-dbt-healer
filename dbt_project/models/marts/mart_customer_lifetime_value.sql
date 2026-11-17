select
    c.customer_id,
    c.customer_name,
    c.segment,
    c.region,
    min(o.order_date)                       as first_order_date,
    max(o.order_date)                       as last_order_date,
    count(distinct o.order_id)              as total_orders,
    sum(o.amount)                           as lifetime_value,
    round(avg(o.amount), 2)                 as avg_order_value,
    datediff('day', min(o.order_date), max(o.order_date)) as customer_tenure_days
from {{ ref('stg_orders') }} o
inner join {{ ref('stg_customers') }} c on c.customer_id = o.customer_id
where o.status = 'completed'
group by c.customer_id, c.customer_name, c.segment, c.region
