-- Staged email-experiment customers with the program arm and the lifecycle
-- lens used for heterogeneity analysis. Every customer bought within the 12
-- months before the email.
create or replace table stg_email as
select
    row_id,
    recency,
    history_segment,
    history,
    mens,
    womens,
    zip_code,
    newbie,
    channel,
    segment                                              as arm,
    (segment <> '{{holdout_arm}}')::int                  as treated,
    visit,
    conversion,
    spend,
    case
        when newbie = 1   then 'New (acquired <12m)'
        when recency <= 3 then 'Active (1-3m)'
        when recency <= 6 then 'Cooling (4-6m)'
        else                   'Lapsing (7-12m)'
    end                                                  as lifecycle_stage,
    case
        when mens = 1 and womens = 1 then 'Both'
        when mens = 1                then 'Mens only'
        else                              'Womens only'
    end                                                  as history_category
from raw_email;

create or replace table email_arm_summary as
select
    arm,
    count(*)                 as customers,
    avg(visit)               as visit_rate,
    avg(conversion)          as conversion_rate,
    avg(spend)               as spend_per_customer,
    sum(visit)               as visits,
    sum(conversion)          as conversions,
    sum(spend)               as spend
from stg_email
group by arm
order by arm;
