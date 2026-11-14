sel                                      -- ERROR: Misspelled SELECT keyword
    o.customer_id,
    c.customer_name,
    c.segment                            -- ERROR: Missing comma after c.segment
    c.region                             -- ERROR: Missing comma after c.region
    min(o.order_date) as first_order_date,
    maxo.order_date) as last_order_date, -- ERROR: Incorrect MAX function syntax
    count(distinct o.order_id) as total_orders,
    sum(o.amount) as lifetime_value,
    avg(o.amount) as avg_order_value,
    datediff('day', min(o.order_date), max(o.order_date)) as customer_tenure_days
from {{ ref('stg_orders') }} o
inner {{ ref('stg_customers') }} c       -- ERROR: Missing JOIN keyword
    on o.customer_id =+ .customer_id     -- ERROR: Invalid operator (=+) and missing table alias before customer_id
whe o.status = 'comp'                    -- ERROR: Misspelled WHERE keyword and incomplete status value
gro by 1, 2, 3, 4                        -- ERROR: Misspelled GROUP BY keyword
