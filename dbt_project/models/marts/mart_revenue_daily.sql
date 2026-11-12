-- Mart: daily revenue aggregated by region and category
select
    o.order_date,
    o.region,
    o.product_category,
    count(distinct o.order_id)    as total_orders,
    count(distinct o.customer_id) as unique_customers,
    sum(o.amount)                 as total_revenue,
    avg(o.amount)                 as avg_order_value
from {{ ref('stg_orders') }} o
where o.status = 'completed'
group by 1, 2, 3