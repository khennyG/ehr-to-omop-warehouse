-- Mart model: OMOP person, built from Synthea patients.
--
-- Independent SQL implementation of transform_person() in
-- src/transform/omop_transformer.py. Deliberately mirrors its gender/race/
-- ethnicity concept_id mappings exactly, value for value, so a discrepancy
-- between this table and the Python pipeline's cdm.person is a real finding
-- a comparison could surface, not an artifact of the two paths using
-- different reference data.

with patients as (
    select * from {{ ref('stg_patients') }}
),

mapped as (
    select
        row_number() over (order by patient_id) as person_id,
        patient_id as person_source_value,
        case gender when 'M' then 8507 when 'F' then 8532 else 0 end as gender_concept_id,
        gender as gender_source_value,
        case lower(race)
            when 'white' then 8527
            when 'black' then 8516
            when 'asian' then 8515
            when 'native' then 8657
            when 'other' then 8522
            else 0
        end as race_concept_id,
        race as race_source_value,
        case lower(ethnicity)
            when 'hispanic' then 38003563
            when 'nonhispanic' then 38003564
            else 0
        end as ethnicity_concept_id,
        ethnicity as ethnicity_source_value,
        extract(year from birth_date)::integer as year_of_birth,
        extract(month from birth_date)::integer as month_of_birth,
        extract(day from birth_date)::integer as day_of_birth,
        birth_date::timestamp as birth_datetime
    from patients
)

select * from mapped
