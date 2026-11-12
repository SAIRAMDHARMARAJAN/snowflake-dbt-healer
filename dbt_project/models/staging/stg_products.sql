-- Staging: raw products
select
    product_id,
    product_name,
    category,
    unit_price,
    is_active
from {{ source('raw', 'raw_products') }}
where product_id is not null
