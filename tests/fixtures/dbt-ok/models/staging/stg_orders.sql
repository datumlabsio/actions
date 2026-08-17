with source as (

    select * from {{ ref('raw_orders') }}

)

select
    order_id,
    customer_id,
    status,
    amount
from source
