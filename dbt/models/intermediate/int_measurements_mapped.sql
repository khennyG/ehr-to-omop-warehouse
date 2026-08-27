-- Intermediate model: resolve numeric observations to OMOP standard concepts.
--
-- Same vocabulary-resolution pattern again, against LOINC. The numeric/text
-- split mirrors transform_measurement / transform_observation in
-- src/transform/omop_transformer.py — this model covers the measurement
-- side (numeric values); the text-valued observation side is Python-only for
-- now (see the dbt project README for what's ported to SQL and what isn't).

with observations as (
    select * from {{ ref('stg_observations') }}
    where try_cast(observation_value as double) is not null
),

source_resolved as (
    select
        o.patient_id,
        o.encounter_id,
        o.observation_datetime,
        o.observation_code,
        o.observation_description,
        o.observation_value::double as value_as_number,
        o.observation_units,
        concept.concept_id as source_concept_id
    from observations o
    left join {{ source('cdm_vocabulary', 'concept') }} concept
        on concept.concept_code = o.observation_code
        and concept.vocabulary_id = 'LOINC'
)

select
    sr.patient_id,
    sr.encounter_id,
    sr.observation_datetime,
    sr.observation_code,
    sr.observation_description,
    sr.value_as_number,
    sr.observation_units,
    coalesce(sr.source_concept_id, 0) as measurement_source_concept_id,
    coalesce(rel.concept_id_2, sr.source_concept_id, 0) as measurement_concept_id
from source_resolved sr
left join {{ source('cdm_vocabulary', 'concept_relationship') }} rel
    on rel.concept_id_1 = sr.source_concept_id
    and rel.relationship_id = 'Maps to'
