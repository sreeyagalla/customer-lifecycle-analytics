-- Fiscal calendar (Dec-Nov years). qidx 1..8 are reporting quarters;
-- qidx 9 (Dec 2011, partial) exists only as follow-up time.
create or replace table fiscal_quarters as
select
    q + 1                                                       as qidx,
    {{first_fiscal_year}} + q // 4                              as fiscal_year,
    q % 4 + 1                                                   as fiscal_quarter,
    'FY' || ({{first_fiscal_year}} + q // 4) || ' Q' || (q % 4 + 1) as label,
    cast(DATE '{{data_start}}' + to_months(3 * q) as date)      as start_date,
    cast(DATE '{{data_start}}' + to_months(3 * q + 3) as date)  as end_date_excl,
    q + 1 <= {{reporting_quarters}}                             as is_reporting
from range(0, {{reporting_quarters}} + 1) t(q);

-- Last day with any invoice in the data: the edge of every follow-up window.
create or replace table data_window as
select
    cast(min(invoice_ts) as date) as data_start_date,
    cast(max(invoice_ts) as date) as data_end_date
from stg_lines;
