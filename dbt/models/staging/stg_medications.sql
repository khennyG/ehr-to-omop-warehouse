-- Staging model: clean pass-through of Synthea medications CSV.
-- No business logic here — just type casting and column renaming
-- for consistency downstream.

with source as (
    select * from {{ source('synthea', 'stg_medications') }}
),

renamed as (
    select
        "PATIENT"                 as patient_id,
        "ENCOUNTER"                as encounter_id,
        "PAYER"                    as payer_id,
        "START"::timestamp         as start_datetime,
        "STOP"::timestamp          as stop_datetime,
        "CODE"                     as medication_code,
        "DESCRIPTION"              as medication_description,
        "BASE_COST"::numeric       as base_cost,
        "PAYER_COVERAGE"::numeric  as payer_coverage,
        "DISPENSES"::integer       as dispenses,
        "TOTALCOST"::numeric       as total_cost,
        "REASONCODE"               as reason_code,
        "REASONDESCRIPTION"        as reason_description
    from source
)

select * from renamed
