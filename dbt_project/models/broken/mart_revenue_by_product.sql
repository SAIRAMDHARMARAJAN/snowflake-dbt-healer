select
    o.order_date,
    p.product_na
    p.category,
    p.unit_pr
    count(distinct o.order_id) as total_order
    sum(o.amount) as total_revenue
from {{ ref('stg_orders') }} o
inner join {{ ref('stg_products') }} p
    on o.product_category = p.category
gr by 1, 2, 3, 4
