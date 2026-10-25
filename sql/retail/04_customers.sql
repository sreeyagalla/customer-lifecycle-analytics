-- One row per identified customer with an order. "First order" means first
-- order observed in the data: the data starts 1 Dec 2009, so customers first
-- seen early in FY2010 may be older customers (see lookback_days).
create or replace table customers as
with ranked as (
    select
        o.*,
        row_number() over (partition by customer_id order by order_ts, invoice) as order_seq
    from orders o
),
firsts as (
    select * from ranked where order_seq = 1
),
totals as (
    select customer_id, count(*) as n_orders, sum(merch_value) as total_merch_value
    from orders
    group by customer_id
),
followup as (
    -- Orders on a later calendar day within the activation window.
    select
        f.customer_id,
        min(o.order_date)                                                as second_order_date,
        sum(case when o.order_date <= f.order_date + {{activation_window_days}}
                 then o.merch_value else 0 end)                           as next_window_revenue
    from firsts f
    join orders o
      on o.customer_id = f.customer_id
     and o.order_date > f.order_date
    group by f.customer_id
),
early_cancel as (
    select distinct f.customer_id
    from firsts f
    join cancellations c
      on c.customer_id = f.customer_id
     and c.cancel_ts >= f.order_ts
     and c.cancel_ts <= f.order_ts + interval 30 day
)
select
    f.customer_id,
    f.invoice                                         as first_invoice,
    f.order_ts                                        as first_order_ts,
    f.order_date                                      as first_order_date,
    f.qidx                                            as first_qidx,
    f.merch_value                                     as first_order_value,
    f.n_products                                      as first_order_products,
    f.units                                           as first_order_units,
    f.country                                         as home_country,
    case when f.country = '{{home_country}}' then 'UK' else 'International' end as segment,
    t.n_orders,
    t.total_merch_value,
    fu.second_order_date,
    fu.second_order_date - f.order_date               as days_to_second_order,
    coalesce(fu.second_order_date <= f.order_date + {{activation_window_days}}, false) as activated_90d,
    f.order_date + {{activation_window_days}} <= w.data_end_date as activation_window_complete,
    coalesce(fu.next_window_revenue, 0)               as next_90d_revenue,
    ec.customer_id is not null                        as early_cancel_30d,
    f.order_date - w.data_start_date                  as lookback_days
from firsts f
join totals t using (customer_id)
cross join data_window w
left join followup fu using (customer_id)
left join early_cancel ec using (customer_id);
