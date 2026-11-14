SELECT
    o.customer_id,
    c.customer_name,
    c.segment,
    c.region,
    min(o.order_date) as first_order_date,
    max(o.order_date) as last_order_date,
    count(distinct o.order_id) as total_orders,
    sum(o.amount) as lifetime_value,
    avg(o.amount) as avg_order_value,
    datediff('day', min(o.order_date), max(o.order_date)) as customer_tenure_days
FROM {{ ref('stg_orders') }} o
INNER JOIN {{ ref('stg_customers') }} c
    ON o.customer_id = c.customer_id
WHERE o.status = 'completed'
GROUP BY o.customer_id, c.customer_name, c.segment, c.region
