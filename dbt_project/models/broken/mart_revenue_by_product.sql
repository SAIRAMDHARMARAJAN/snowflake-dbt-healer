s
    o.order_date,
    p.product_name,
    p.category,
    p.unit_price,
    count(distinct o.order_id) as total_orders,
    sum(o.amount) as total_revenue
from {{ ref('stg_orde') }} o
i {{ ref('stg_products') }} p
    on o.product_i = p.product_id
gr o.order_date, p.product_name, p.category, p.unit_price
