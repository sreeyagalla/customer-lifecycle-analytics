-- Customer x fiscal quarter, from each customer's first active quarter to the
-- last reporting quarter, with a lifecycle status per row:
--   new          active, no earlier order in the data
--   retained     active, and active the previous quarter
--   reactivated  active, inactive the previous quarter, active some time before
--   lapsed       inactive, but active the previous quarter
--   dormant      inactive for two or more quarters
-- quarters_since_last_active lets the scorecard apply any lookback rule,
-- e.g. "new with a 3-quarter lookback" = active and (no prior order or gap > 3).
create or replace table customer_quarter as
with activity as (
    select
        customer_id,
        qidx,
        count(*)                 as orders,
        sum(merch_value)         as gross_value,
        min(order_date)          as first_order_date_in_q
    from orders
    group by customer_id, qidx
),
next_order as (
    -- First order on a later calendar day than the customer's first order of the quarter.
    select a.customer_id, a.qidx, min(o.order_date) as next_order_date
    from activity a
    join orders o
      on o.customer_id = a.customer_id
     and o.order_date > a.first_order_date_in_q
    group by a.customer_id, a.qidx
),
cancels as (
    select customer_id, qidx, sum(merch_value) as cancel_value
    from cancellations
    group by customer_id, qidx
),
grid as (
    select c.customer_id, c.segment, q.qidx
    from customers c
    join fiscal_quarters q
      on q.qidx >= c.first_qidx
     and q.is_reporting
),
joined as (
    select
        g.customer_id,
        g.segment,
        g.qidx,
        a.orders is not null                              as is_active,
        coalesce(a.orders, 0)                             as orders,
        coalesce(a.gross_value, 0)                        as gross_value,
        coalesce(x.cancel_value, 0)                       as cancel_value,
        a.first_order_date_in_q,
        n.next_order_date
    from grid g
    left join activity a using (customer_id, qidx)
    left join cancels  x using (customer_id, qidx)
    left join next_order n using (customer_id, qidx)
),
history as (
    select
        j.*,
        max(case when is_active then qidx end) over (
            partition by customer_id order by qidx
            rows between unbounded preceding and 1 preceding
        )                                                  as last_active_before,
        coalesce(lag(is_active, 1) over (partition by customer_id order by qidx), false) as active_prev,
        coalesce(lag(is_active, 2) over (partition by customer_id order by qidx), false) as active_prev2
    from joined j
)
select
    h.customer_id,
    h.segment,
    h.qidx,
    h.is_active,
    h.orders,
    h.gross_value,
    h.cancel_value,
    h.gross_value + h.cancel_value                         as net_value,
    h.last_active_before,
    h.qidx - h.last_active_before                          as quarters_since_last_active,
    h.active_prev,
    h.active_prev2,
    case
        when h.is_active and h.last_active_before is null then 'new'
        when h.is_active and h.active_prev                then 'retained'
        when h.is_active                                  then 'reactivated'
        when h.active_prev                                then 'lapsed'
        else 'dormant'
    end                                                    as status,
    h.first_order_date_in_q,
    h.next_order_date,
    coalesce(h.next_order_date <= h.first_order_date_in_q + {{activation_window_days}}, false)
                                                           as activated_90d
from history h;
