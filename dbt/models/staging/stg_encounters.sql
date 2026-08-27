-- Staging model: clean pass-through of Synthea encounters CSV.
-- No business logic here — just type casting and column renaming
-- for consistency downstream.

with source as (
    select * from {{ source('synthea', 'stg_encounters') }}
),

renamed as (
    select
        "Id"                            as encounter_id,
        "PATIENT"                       as patient_id,
        "ORGANIZATION"                  as organization_id,
        "PROVIDER"                      as provider_id,
        "PAYER"                         as payer_id,
        "START"::timestamp              as start_datetime,
        "STOP"::timestamp               as stop_datetime,
        "ENCOUNTERCLASS"                as encounter_class,
        "CODE"                          as encounter_code,
        "DESCRIPTION"                   as encounter_description,
        "BASE_ENCOUNTER_COST"::numeric  as base_encounter_cost,
        "TOTAL_CLAIM_COST"::numeric     as total_claim_cost,
        "PAYER_COVERAGE"::numeric       as payer_coverage,
        "REASONCODE"                    as reason_code,
        "REASONDESCRIPTION"             as reason_description
    from source
)

select * from renamed
