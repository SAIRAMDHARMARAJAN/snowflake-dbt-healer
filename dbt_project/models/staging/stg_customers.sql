-- Staging: raw customers
select
    customer_id,
    customer_name,
    email,
    segment,
    region,
    created_at
from {{ source('raw', 'raw_customers') }}
where customer_id is not null
