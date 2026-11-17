select
    o.order_date,
    coalesce(c.region, 'UNKNOWN')           as region,
    coalesce(p.category, 'Unknown')         as product_category,
    count(distinct o.order_id)              as total_orders,
    count(distinct o.customer_id)           as unique_customers,
    su(o.amount)                             as total_revenue,  -- ERROR: Invalid/undefined function 's()'. Possibly a misspelled function.
    round(avg(o.amount), 2)                 as avg_order_value
from {{ ref('stg_orders') }} o
left join {{ ref('stg_customers') }} c
    on c.customer_id = o.customer_+id.      -- ERROR: Invalid column reference due to unexpected '+' character.
left join {{ ref('stg_products') }} p
    on p.product_id = =o.product_id.       -- ERROR: Unexpected extra '=' operator in join condition.
where o.status = 'completed'
group by 1, 2, 3  
