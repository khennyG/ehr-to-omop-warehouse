-- Intermediate model: resolve condition codes to OMOP standard concepts.
--
-- This is the SQL-native equivalent of what VocabularyMapper.resolve() does in
-- Python during transform — the left join against concept_relationship on
-- relationship_id = 'Maps to' is exactly the hop
-- VocabularyMapper.to_standard() walks in memory, against the same
-- cdm.concept / cdm.concept_relationship tables (populated by
-- src/load/warehouse_loader.py's load_vocabulary(), not by dbt — see the
-- cdm_vocabulary source below).
--
-- Deduplication happens here too: Synthea occasionally emits the same
-- condition twice for one encounter, a known quirk of how its disease modules
-- compose. A raw count of condition rows without this would overstate how
-- many distinct problems a patient actually has.

with conditions as (
    select * from {{ ref('stg_conditions') }}
),

source_resolved as (
    select
        c.patient_id,
        c.encounter_id,
        c.condition_start_date,
        c.condition_stop_date,
        c.condition_code,
        c.condition_description,
        concept.concept_id as source_concept_id
    from conditions c
    left join {{ source('cdm_vocabulary', 'concept') }} concept
        on concept.concept_code = c.condition_code
        and concept.vocabulary_id = 'SNOMED'
),

standard_resolved as (
    select
        sr.*,
        coalesce(rel.concept_id_2, sr.source_concept_id, 0) as standard_concept_id
    from source_resolved sr
    left join {{ source('cdm_vocabulary', 'concept_relationship') }} rel
        on rel.concept_id_1 = sr.source_concept_id
        and rel.relationship_id = 'Maps to'
),

deduplicated as (
    select
        *,
        row_number() over (
            partition by patient_id, encounter_id, condition_code, condition_start_date
            order by condition_start_date
        ) as dedup_rank
    from standard_resolved
)

select
    patient_id,
    encounter_id,
    condition_start_date,
    condition_stop_date,
    condition_code,
    condition_description,
    coalesce(source_concept_id, 0) as condition_source_concept_id,
    standard_concept_id as condition_concept_id
from deduplicated
where dedup_rank = 1
