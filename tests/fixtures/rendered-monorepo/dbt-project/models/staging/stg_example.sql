with source as (

    select * from {{ ref('raw_example') }}

)

select
    event_id,
    customer_id,
    status,
    amount
from source
