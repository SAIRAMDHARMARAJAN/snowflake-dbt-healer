with source as (
    select * from {{ source('raw', 'raw_customers') }}
),

cleaned as (
    select
        upper(trim(customer_id))                  as customer_id,
        trim(customer_name)                       as customer_name,
        nullif(lower(trim(email)), '')            as email,
        case lower(trim(segment))
            when 'enterprise' then 'Enterprise'
            when 'mid-market' then 'Mid-Market'
            when 'smb'        then 'SMB'
            else 'Unknown'
        end                                       as segment,
        coalesce(upper(nullif(trim(region), '')), 'UNKNOWN') as region,
        created_at,
        updated_at,
        loaded_at
    from source
    where nullif(trim(customer_id), '') is not null
)

select *
from cleaned
qualify row_number() over (
    partition by customer_id
    order by updated_at desc nulls last, loaded_at desc
) = 1
