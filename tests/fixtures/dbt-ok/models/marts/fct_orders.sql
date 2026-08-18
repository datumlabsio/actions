with orders as (

    select * from {{ ref('stg_orders') }}

)

select
    customer_id,
    count(*) as order_count,
    sum(amount) as total_amount
from orders
where status = 'completed'
group by customer_id
