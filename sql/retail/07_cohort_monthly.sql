-- Monthly acquisition cohorts (month of first observed order) and the share of
-- each cohort ordering again k months later. lookback_months says how much
-- history sits behind the cohort; cohorts with < 12 months are mostly existing
-- customers seen for the first time, not new ones.
create or replace table cohort_monthly as
with cust as (
    select customer_id, segment, date_trunc('month', first_order_date) as cohort_month
    from customers
),
active_months as (
    select distinct customer_id, date_trunc('month', order_date) as active_month
    from orders
),
sizes as (
    select coalesce(segment, 'All') as segment, cohort_month, count(*) as cohort_size
    from cust
    group by grouping sets ((segment, cohort_month), (cohort_month))
),
cust_months as (
    select
        c.segment,
        c.cohort_month,
        date_diff('month', c.cohort_month, a.active_month)           as months_since
    from cust c
    join active_months a using (customer_id)
    where a.active_month >= c.cohort_month
),
activity as (
    select
        coalesce(segment, 'All')                                     as segment,
        cohort_month,
        months_since,
        count(*)                                                     as active_customers
    from cust_months
    group by grouping sets ((segment, cohort_month, months_since), (cohort_month, months_since))
)
select
    a.segment,
    a.cohort_month,
    date_diff('month', DATE '{{data_start}}', a.cohort_month)        as lookback_months,
    a.months_since,
    s.cohort_size,
    a.active_customers,
    a.active_customers / s.cohort_size                               as active_share,
    -- the last calendar month is partial (data ends 9 Dec 2011)
    a.cohort_month + to_months(a.months_since) >= date_trunc('month', (select data_end_date from data_window))
                                                                     as partial_month
from activity a
join sizes s using (segment, cohort_month)
order by a.segment, a.cohort_month, a.months_since;
