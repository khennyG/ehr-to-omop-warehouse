-- Staging model: clean pass-through of Synthea procedures CSV.
-- No business logic here — just type casting and column renaming
-- for consistency downstream.

with source as (
    select * from {{ source('synthea', 'stg_procedures') }}
),

renamed as (
    select
        "PATIENT"            as patient_id,
        "ENCOUNTER"          as encounter_id,
        "START"::timestamp   as start_datetime,
        "STOP"::timestamp    as stop_datetime,
        "CODE"               as procedure_code,
        "DESCRIPTION"        as procedure_description,
        "BASE_COST"::numeric as base_cost,
        "REASONCODE"         as reason_code,
        "REASONDESCRIPTION"  as reason_description
    from source
)

select * from renamed
