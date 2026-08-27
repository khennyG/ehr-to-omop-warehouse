-- Staging model: clean pass-through of Synthea patients CSV.
-- No business logic here — just type casting and column renaming
-- for consistency downstream.

with source as (
    select * from {{ source('synthea', 'stg_patients') }}
),

renamed as (
    select
        "Id"                   as patient_id,
        "BIRTHDATE"::date      as birth_date,
        "DEATHDATE"::date      as death_date,
        "FIRST"                as first_name,
        "LAST"                 as last_name,
        "GENDER"               as gender,
        "RACE"                 as race,
        "ETHNICITY"            as ethnicity,
        "CITY"                 as city,
        "STATE"                as state,
        "COUNTY"               as county,
        "ZIP"                  as zip_code,
        "LAT"::numeric         as latitude,
        "LON"::numeric         as longitude,
        "INCOME"::numeric      as income
    from source
)

select * from renamed
