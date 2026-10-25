-- Growth accounting by quarter and segment:
--   active(q) = new(q) + retained(q) + reactivated(q)
--   lapsed(q) = active(q-1) - retained(q)
-- "new" here is first-seen-in-data; FY2010 quarters have little history behind
-- them, so their new/reactivated split is flagged history_limited.
create or replace table lifecycle_quarterly as
with by_segment as (
    select
        coalesce(cq.segment, 'All')                                  as segment,
        cq.qidx,
        count(*) filter (where cq.is_active)                         as active_customers,
        count(*) filter (where cq.status = 'new')                    as new_customers,
        count(*) filter (where cq.status = 'retained')               as retained_customers,
        count(*) filter (where cq.status = 'reactivated')            as reactivated_customers,
        count(*) filter (where cq.status = 'lapsed')                 as lapsed_customers,
        count(*) filter (where cq.active_prev)                       as prior_active_customers,
        sum(cq.orders)                                               as orders,
        sum(cq.gross_value)                                          as gross_value,
        sum(cq.net_value) filter (where cq.is_active)                as active_net_value
    from customer_quarter cq
    group by grouping sets ((cq.segment, cq.qidx), (cq.qidx))
)
select
    b.segment,
    b.qidx,
    q.label,
    q.fiscal_year,
    q.fiscal_quarter,
    b.active_customers,
    b.new_customers,
    b.retained_customers,
    b.reactivated_customers,
    b.lapsed_customers,
    b.prior_active_customers,
    b.retained_customers / nullif(b.prior_active_customers, 0)       as retention_rate,
    b.orders,
    b.gross_value,
    b.active_net_value / nullif(b.active_customers, 0)               as revenue_per_active,
    q.fiscal_year = {{first_fiscal_year}}                            as history_limited
from by_segment b
join fiscal_quarters q using (qidx)
order by b.segment, b.qidx;
