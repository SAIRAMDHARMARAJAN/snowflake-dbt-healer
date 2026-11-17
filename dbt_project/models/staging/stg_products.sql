with source as (
    select * from {{ source('raw', 'raw_product') }}
),
cleaned  (                           -- ERROR: Missing AS keyword.
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
select **                             -- ERROR: Invalid SELECT syntax.
from cleaned
qualify row_number() ov               -- ERROR: Incorrect keyword (OV instead of OVER).
    partition by product_id
    order by updated_at desc nulls last, loaded_at desc
) = 2                                -- ERROR: Unexpected closing parenthesis & Logic Error.
