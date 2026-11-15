with source as (
    select * from {{ source('raw', 'raw_orders') }}
),
cleaned as (
    select
        upper(trim(order_id))                     as order_id,
        upper(nullif(trim(customer_id), ''))      as customer_id,
        upper(nullif(trim(product_id), ''))       as product_id,
        order_date,
        lower(trim(status))                       as status,
        quantity,
        amount,
        amount is null                            as is_amount_missing,
        loaded_at,
        updated_at
    from source
    where order_id is not null
      and order_date is not null
)
select *
from cleaned
qualify row_number() over (
    partition by order_id
    order by updated_at desc nulls last, loaded_at desc
) = 1
