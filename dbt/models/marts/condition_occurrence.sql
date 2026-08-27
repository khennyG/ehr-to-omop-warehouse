-- Mart model: OMOP condition_occurrence, built from mapped Synthea conditions.

with conditions as (
    select * from {{ ref('int_conditions_mapped') }}
),

persons as (
    select * from {{ ref('person') }}
),

visits as (
    select * from {{ ref('visit_occurrence') }}
),

joined as (
    select
        row_number() over (order by c.condition_start_date, p.person_id) as condition_occurrence_id,
        p.person_id,
        c.condition_concept_id,
        c.condition_start_date,
        c.condition_stop_date as condition_end_date,
        32817 as condition_type_concept_id,
        c.condition_code as condition_source_value,
        c.condition_source_concept_id,
        v.visit_occurrence_id
    from conditions c
    inner join persons p on p.person_source_value = c.patient_id
    left join visits v on v.visit_source_value = c.encounter_id
)

select * from joined
