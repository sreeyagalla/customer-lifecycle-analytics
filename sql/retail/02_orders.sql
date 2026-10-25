-- One row per customer order: a non-cancelled invoice from an identified
-- customer with positive merchandise value (fees, postage and zero-price lines
-- excluded).
create or replace table orders as
select
    invoice,
    any_value(customer_id)            as customer_id,
    min(invoice_ts)                   as order_ts,
    cast(min(invoice_ts) as date)     as order_date,
    fq(min(invoice_ts))               as qidx,
    min(country)                      as country,
    sum(line_value)                   as merch_value,
    count(*)                          as n_lines,
    count(distinct stock_code)        as n_products,
    sum(quantity)                     as units
from stg_lines
where customer_id is not null
  and not is_cancellation
  and not is_bad_debt_adjustment
  and is_merchandise
  and unit_price > 0
  and quantity > 0
group by invoice
having sum(line_value) > 0;

-- Merchandise cancellations from identified customers (value is negative),
-- attributed to the quarter in which they were raised.
create or replace table cancellations as
select
    invoice,
    any_value(customer_id)            as customer_id,
    min(invoice_ts)                   as cancel_ts,
    fq(min(invoice_ts))               as qidx,
    sum(line_value)                   as merch_value
from stg_lines
where customer_id is not null
  and is_cancellation
  and is_merchandise
group by invoice;
