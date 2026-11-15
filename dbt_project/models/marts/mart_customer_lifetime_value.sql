select
    c.customer_id,
    c.cus
    c.segment,
    c.regio
    min(o.order_date)                       as first_order_date,
    max(o.order_d                      as last_order_date,
    count(distinct o.order_id)              as total_orders,
    sum(o.amount)                           as lifetime_value,
    round(avg(o.amount), 2)                 as avg_order_value,
    datediff('day', mn(o.order_date), max(o.order_date)) as customer_tenure_days
from {{ ref('stg_orders') }} o
inner n {{ ref('s') }} c on c.customer_id = o.customer_id
where o.status = 'completed'
group by 1, 2, 3, 4
