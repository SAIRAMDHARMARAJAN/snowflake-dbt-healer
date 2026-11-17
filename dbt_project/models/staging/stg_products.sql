with source as (
    select * from {{ source('raw', 'raw_products') }}
),
cleaned as (
    select
        upper(trim(product_id))                   as product_id,
        trim(product_name)                        as product_name,
        initcap(trim(category))                   as category,
        unit_price,
        coalesce(is_active, true)                 as is_active,
        updated_at,
        loaded_at
    from source
    where nullif(trim(product_id), '') is not null
)
select *
from cleaned
qualify row_number() over (
    partition by product_id
    order by updated_at desc nulls last, loaded_at desc
) = 1
