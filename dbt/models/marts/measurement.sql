-- Mart model: OMOP measurement, built from mapped numeric Synthea observations.

with measurements as (
    select * from {{ ref('int_measurements_mapped') }}
),

persons as (
    select * from {{ ref('person') }}
),

visits as (
    select * from {{ ref('visit_occurrence') }}
),

joined as (
    select
        row_number() over (order by m.observation_datetime, p.person_id) as measurement_id,
        p.person_id,
        m.measurement_concept_id,
        m.observation_datetime::date as measurement_date,
        m.observation_datetime as measurement_datetime,
        32817 as measurement_type_concept_id,  -- EHR; matches TYPE_CONCEPT in omop_transformer.py
        m.value_as_number,
        m.observation_units as unit_source_value,
        m.observation_code as measurement_source_value,
        m.measurement_source_concept_id,
        v.visit_occurrence_id
    from measurements m
    inner join persons p on p.person_source_value = m.patient_id
    left join visits v on v.visit_source_value = m.encounter_id
)

select * from joined
