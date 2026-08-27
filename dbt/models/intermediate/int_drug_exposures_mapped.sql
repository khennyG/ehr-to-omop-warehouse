-- Intermediate model: resolve medication codes to OMOP standard concepts.
--
-- Same pattern as int_conditions_mapped.sql, against RxNorm instead of
-- SNOMED — the vocabulary_id is the only thing that changes between "map a
-- condition" and "map a drug exposure" here, same as in
-- src/transform/omop_transformer.py, where transform_condition_occurrence
-- and transform_drug_exposure differ only in which vocabulary_id they pass
-- to VocabularyMapper.resolve().

with medications as (
    select * from {{ ref('stg_medications') }}
),

source_resolved as (
    select
        m.patient_id,
        m.encounter_id,
        m.start_datetime,
        m.stop_datetime,
        m.medication_code,
        m.medication_description,
        m.dispenses,
        concept.concept_id as source_concept_id
    from medications m
    left join {{ source('cdm_vocabulary', 'concept') }} concept
        on concept.concept_code = m.medication_code
        and concept.vocabulary_id = 'RxNorm'
),

standard_resolved as (
    select
        sr.*,
        coalesce(rel.concept_id_2, sr.source_concept_id, 0) as standard_concept_id
    from source_resolved sr
    left join {{ source('cdm_vocabulary', 'concept_relationship') }} rel
        on rel.concept_id_1 = sr.source_concept_id
        and rel.relationship_id = 'Maps to'
)

select
    patient_id,
    encounter_id,
    start_datetime,
    -- Mirrors the fallback in transform_drug_exposure: OMOP requires
    -- drug_exposure_end_date to be populated, and a still-open prescription
    -- (no STOP recorded) is estimated at dispenses * 30 days rather than
    -- collapsed to a single day, which would understate a chronic,
    -- repeatedly-refilled medication's real exposure.
    coalesce(stop_datetime, start_datetime + (dispenses * interval '30 days')) as end_datetime,
    stop_datetime as verbatim_end_datetime,
    medication_code,
    medication_description,
    dispenses,
    coalesce(source_concept_id, 0) as drug_source_concept_id,
    standard_concept_id as drug_concept_id
from standard_resolved
