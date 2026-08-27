with events as (

    select * from {{ ref('stg_example') }}

)

select
    customer_id,
    count(*) as event_count,
    sum(amount) as total_amount
from events
where status = 'completed'
group by customer_id
