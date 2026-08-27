-- Staging model: clean pass-through of Synthea observations CSV.
-- No business logic here — just type casting and column renaming
-- for consistency downstream. VALUE stays text: it mixes numeric labs and
-- categorical findings in the source, same as src/transform/omop_transformer.py's
-- split into measurement (numeric) and observation (everything else) handles
-- one layer up, not here.

with source as (
    select * from {{ source('synthea', 'stg_observations') }}
),

renamed as (
    select
        "PATIENT"          as patient_id,
        "ENCOUNTER"        as encounter_id,
        "DATE"::timestamp  as observation_datetime,
        "CATEGORY"         as observation_category,
        "CODE"             as observation_code,
        "DESCRIPTION"      as observation_description,
        "VALUE"            as observation_value,
        "UNITS"            as observation_units,
        "TYPE"             as value_type
    from source
)

select * from renamed
