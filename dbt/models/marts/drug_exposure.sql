-- Mart model: OMOP drug_exposure, built from mapped Synthea medications.

with drugs as (
    select * from {{ ref('int_drug_exposures_mapped') }}
),

persons as (
    select * from {{ ref('person') }}
),

visits as (
    select * from {{ ref('visit_occurrence') }}
),

joined as (
    select
        row_number() over (order by d.start_datetime, p.person_id) as drug_exposure_id,
        p.person_id,
        d.drug_concept_id,
        d.start_datetime::date as drug_exposure_start_date,
        d.start_datetime as drug_exposure_start_datetime,
        d.end_datetime::date as drug_exposure_end_date,
        d.end_datetime as drug_exposure_end_datetime,
        d.verbatim_end_datetime::date as verbatim_end_date,
        32838 as drug_type_concept_id,  -- Prescription written; matches TYPE_CONCEPT in omop_transformer.py
        d.dispenses as quantity,
        d.medication_code as drug_source_value,
        d.drug_source_concept_id,
        v.visit_occurrence_id
    from drugs d
    inner join persons p on p.person_source_value = d.patient_id
    left join visits v on v.visit_source_value = d.encounter_id
)

select * from joined
