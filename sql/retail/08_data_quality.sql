-- Every cleaning step, counted, so the dashboard and README can show exactly
-- what was removed and why.
create or replace table data_quality as
with raw_counts as (
    select
        count(*)                                                               as raw_lines,
        count(*) filter (where source_sheet = '{{overlap_sheet}}'
                         and invoice_ts >= TIMESTAMP '{{overlap_from}}')       as overlap_lines
    from raw_lines
)
select 1 as step, 'Lines in the published workbook (both sheets)' as description, raw_lines as n from raw_counts
union all
select 2, 'Removed: sheet overlap (1-9 Dec 2010 appears in both sheets)', overlap_lines from raw_counts
union all
select 3, 'Removed: exact duplicate lines', (select raw_lines - overlap_lines from raw_counts) - (select count(*) from stg_lines)
union all
select 4, 'Staged lines', (select count(*) from stg_lines)
union all
select 5, 'Staged lines with no customer ID (excluded from customer analysis)', (select count(*) from stg_lines where customer_id is null)
union all
select 6, 'Staged lines that are cancellations', (select count(*) from stg_lines where is_cancellation)
union all
select 7, 'Staged lines that are fees, postage, adjustments or vouchers', (select count(*) from stg_lines where not is_merchandise)
union all
select 8, 'Customer orders (invoices with positive merchandise value)', (select count(*) from orders)
union all
select 9, 'Identified customers with at least one order', (select count(*) from customers)
order by step;
