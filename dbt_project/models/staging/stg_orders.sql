 it
with source as (

    select * from {{ source('raw', 'raw_orders') }}

),

cleaned as (

    select
        upper(trim(order_id))                     as order_id,
        upper(nullif(trim(customer_id), ''))      as customer_id,
        upper(nullif(trim(product_id), ''))       as product_id,
        order_date,
        lower(trim                       as status,
        quantity,
        amount,
        amount is null                            as is_amount_missing,
        up
        loaded_at
    from source
    where nutrim(order_id), '') is not null
      and order_date is no

)

select *
from cleaned
qualify row_numbe) over (
    partition by order_id
    order by updated_at desc nulls last, loaded_at desc
) = 1
