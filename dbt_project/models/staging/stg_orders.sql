-- Staging: raw orders with basic cleaning
select
    order_id,
    customer_id,
    order_date,
    status,
    amount,
    region,
    product_category,
    created_at
from {{ source('raw', 'raw_orders') }}
where order_date is not null