-- Staged invoice lines.
-- 1. Drop the workbook overlap: the 2009-2010 sheet repeats every invoice of
--    1-9 Dec 2010 that the 2010-2011 sheet also carries.
-- 2. Drop exact duplicate lines (same invoice, item, quantity, time, price, customer).
-- 3. Classify each line: cancellation, bad-debt adjustment, merchandise or not.

create or replace macro fq(ts) as
    (date_diff('month', DATE '{{data_start}}', cast(ts as date)) // 3) + 1;

create or replace table stg_lines as
with no_overlap as (
    select *
    from raw_lines
    where not (source_sheet = '{{overlap_sheet}}'
               and invoice_ts >= TIMESTAMP '{{overlap_from}}')
),
distinct_lines as (
    select distinct
        invoice, stock_code, description, quantity, invoice_ts,
        unit_price, customer_id, country
    from no_overlap
)
select
    d.invoice,
    d.stock_code,
    d.description,
    d.quantity,
    d.invoice_ts,
    d.unit_price,
    d.customer_id,
    d.country,
    d.quantity * d.unit_price                         as line_value,
    starts_with(d.invoice, 'C')                       as is_cancellation,
    starts_with(d.invoice, 'A')                       as is_bad_debt_adjustment,
    not (
        d.stock_code in (select code from cfg_non_merch_codes)
        or exists (select 1 from cfg_non_merch_prefixes p
                   where starts_with(d.stock_code, p.prefix))
    )                                                 as is_merchandise
from distinct_lines d;
