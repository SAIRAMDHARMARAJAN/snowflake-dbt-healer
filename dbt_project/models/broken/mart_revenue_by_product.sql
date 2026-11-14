sel                                            -- Spelling mistake: SELECT statement
    o.order_date,
    p.product_name,
    p.category,
    p.unit_price                               -- syntax_error (comma missing)
    count(distinct o.order_id) as total_order,
    sum(o.amount) as total_reve                -- Spelling mistake
from {{ ref('stg_orders') }} o
inner {{ ref('stg_products') }} p
    on o.product_category =+ p.category       -- syntax error (Additional '+' symbol)
group by 1, 2, 3, 4
