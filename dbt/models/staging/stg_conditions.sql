-- Staging model: clean pass-through of Synthea conditions CSV.
-- No business logic here — just type casting and column renaming
-- for consistency downstream.

with source as (
    select * from {{ source('synthea', 'stg_conditions') }}
),

renamed as (
    select
        "PATIENT"      as patient_id,
        "ENCOUNTER"    as encounter_id,
        "START"::date  as condition_start_date,
        "STOP"::date   as condition_stop_date,
        "CODE"         as condition_code,
        "DESCRIPTION"  as condition_description
    from source
)

select * from renamed
