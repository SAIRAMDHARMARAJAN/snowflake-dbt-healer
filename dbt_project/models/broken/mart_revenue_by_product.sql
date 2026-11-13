SELECT
    o.order_date,
    p.product_name,
    p.category,
    p.unit_price,
    count(distinct o.order_id) as total_order,
    sum(o.amount) as total_revenue
FROM {{ ref('stg_orders') }} o
INNER JOIN {{ ref('stg_products') }} p
    ON o.product_category = p.category
GROUP BY 1, 2, 3, 4
