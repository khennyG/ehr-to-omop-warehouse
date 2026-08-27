-- Mart model: OMOP visit_occurrence, built from Synthea encounters.
--
-- visit_source_value holds the raw Synthea encounter id rather than the
-- encounter class — the class is already fully captured by visit_concept_id,
-- and keeping the source id here is what lets condition_occurrence.sql and
-- drug_exposure.sql join a clinical event back to the visit it happened in.

with encounters as (
    select * from {{ ref('stg_encounters') }}
),

persons as (
    select * from {{ ref('person') }}
),

mapped as (
    select
        row_number() over (order by e.start_datetime, e.encounter_id) as visit_occurrence_id,
        p.person_id,
        case lower(e.encounter_class)
            when 'inpatient' then 9201
            when 'emergency' then 9203
            when 'urgentcare' then 9203
            else 9202
        end as visit_concept_id,
        e.start_datetime::date as visit_start_date,
        e.start_datetime as visit_start_datetime,
        e.stop_datetime::date as visit_end_date,
        e.stop_datetime as visit_end_datetime,
        32817 as visit_type_concept_id,
        e.encounter_id as visit_source_value
    from encounters e
    inner join persons p on p.person_source_value = e.patient_id
)

select * from mapped
