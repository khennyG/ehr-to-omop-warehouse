-- OMOP CDM v5.4 — table definitions.
--
-- This mirrors the table set OHDSI publishes for the Common Data Model, grouped the
-- same way their own documentation groups it: vocabulary, clinical data, health
-- system, health economics, derived elements, cohort, and metadata. Everything here
-- is postgres syntax; the docker-compose Postgres container mounts this directory as
-- /docker-entrypoint-initdb.d and runs the .sql files in the order their filenames
-- sort, which is why this one is prefixed 01 — tables have to exist before
-- 02_primary_keys.sql and 03_constraints.sql can reference them.
--
-- Not every table here gets populated by this pipeline. The nine clinical tables the
-- transform stage actually writes to (person, observation_period, visit_occurrence,
-- condition_occurrence, drug_exposure, procedure_occurrence, measurement,
-- observation, death) and the vocabulary tables the mapper queries (concept,
-- concept_relationship, vocabulary, domain, concept_class) carry real rows. The rest
-- — visit_detail, device_exposure, note, note_nlp, specimen, fact_relationship, the
-- health system and health economics tables, the *_era derived tables, cohort and
-- cohort_definition — exist because a CDM that's missing a fifth of its schema isn't
-- actually a CDM. They're valid, correctly-keyed, and empty, ready for a later sprint
-- that has device data, notes, or claims to put in them.

create schema if not exists cdm;
set search_path to cdm;

-- ============================================================================
-- Standardized vocabulary
-- ============================================================================

create table concept (
    concept_id                 integer         not null,
    concept_name                varchar(255)    not null,
    domain_id                    varchar(20)     not null,
    vocabulary_id                 varchar(20)     not null,
    concept_class_id               varchar(20)     not null,
    standard_concept                 varchar(1),
    concept_code                       varchar(50)     not null,
    valid_start_date                     date            not null,
    valid_end_date                         date            not null,
    invalid_reason                           varchar(1)
);

create table vocabulary (
    vocabulary_id             varchar(20)     not null,
    vocabulary_name             varchar(255)    not null,
    vocabulary_reference          varchar(255),
    vocabulary_version              varchar(255),
    vocabulary_concept_id             integer         not null
);

create table domain (
    domain_id              varchar(20)     not null,
    domain_name              varchar(255)    not null,
    domain_concept_id          integer         not null
);

create table concept_class (
    concept_class_id            varchar(20)     not null,
    concept_class_name            varchar(255)    not null,
    concept_class_concept_id        integer         not null
);

create table concept_relationship (
    concept_id_1               integer         not null,
    concept_id_2                 integer         not null,
    relationship_id                varchar(20)     not null,
    valid_start_date                 date            not null,
    valid_end_date                     date            not null,
    invalid_reason                       varchar(1)
);

create table relationship (
    relationship_id              varchar(20)     not null,
    relationship_name              varchar(255)    not null,
    is_hierarchical                  varchar(1)      not null,
    defines_ancestry                   varchar(1)      not null,
    reverse_relationship_id              varchar(20)     not null,
    relationship_concept_id                integer         not null
);

create table concept_synonym (
    concept_id                 integer         not null,
    concept_synonym_name         varchar(1000)   not null,
    language_concept_id            integer         not null
);

create table concept_ancestor (
    ancestor_concept_id           integer     not null,
    descendant_concept_id           integer     not null,
    min_levels_of_separation           integer     not null,
    max_levels_of_separation             integer     not null
);

create table source_to_concept_map (
    source_code                 varchar(50)     not null,
    source_concept_id             integer         not null,
    source_vocabulary_id            varchar(20)     not null,
    source_code_description           varchar(255),
    target_concept_id                   integer         not null,
    target_vocabulary_id                  varchar(20)     not null,
    valid_start_date                        date            not null,
    valid_end_date                            date            not null,
    invalid_reason                              varchar(1)
);

create table drug_strength (
    drug_concept_id                integer     not null,
    ingredient_concept_id            integer     not null,
    amount_value                       numeric,
    amount_unit_concept_id               integer,
    numerator_value                        numeric,
    numerator_unit_concept_id                integer,
    denominator_value                          numeric,
    denominator_unit_concept_id                  integer,
    box_size                                       integer,
    valid_start_date                                 date        not null,
    valid_end_date                                     date        not null,
    invalid_reason                                       varchar(1)
);

-- ============================================================================
-- Standardized clinical data
-- ============================================================================

create table person (
    person_id                       integer         not null,
    gender_concept_id                 integer         not null,
    year_of_birth                       integer         not null,
    month_of_birth                        integer,
    day_of_birth                            integer,
    birth_datetime                            timestamp,
    race_concept_id                             integer         not null,
    ethnicity_concept_id                          integer         not null,
    location_id                                     integer,
    provider_id                                       integer,
    care_site_id                                        integer,
    person_source_value                                   varchar(50),
    gender_source_value                                     varchar(50),
    gender_source_concept_id                                  integer,
    race_source_value                                           varchar(50),
    race_source_concept_id                                        integer,
    ethnicity_source_value                                          varchar(50),
    ethnicity_source_concept_id                                       integer
);

create table observation_period (
    observation_period_id             integer     not null,
    person_id                           integer     not null,
    observation_period_start_date         date        not null,
    observation_period_end_date             date        not null,
    period_type_concept_id                    integer     not null
);

create table visit_occurrence (
    visit_occurrence_id                integer     not null,
    person_id                            integer     not null,
    visit_concept_id                       integer     not null,
    visit_start_date                         date        not null,
    visit_start_datetime                       timestamp,
    visit_end_date                               date        not null,
    visit_end_datetime                             timestamp,
    visit_type_concept_id                            integer     not null,
    provider_id                                        integer,
    care_site_id                                         integer,
    visit_source_value                                     varchar(50),
    visit_source_concept_id                                  integer,
    admitted_from_concept_id                                   integer,
    admitted_from_source_value                                   varchar(50),
    discharged_to_concept_id                                       integer,
    discharged_to_source_value                                       varchar(50),
    preceding_visit_occurrence_id                                      integer
);

create table visit_detail (
    visit_detail_id                     integer     not null,
    person_id                             integer     not null,
    visit_detail_concept_id                 integer     not null,
    visit_detail_start_date                   date        not null,
    visit_detail_start_datetime                 timestamp,
    visit_detail_end_date                         date        not null,
    visit_detail_end_datetime                       timestamp,
    visit_detail_type_concept_id                      integer     not null,
    provider_id                                         integer,
    care_site_id                                          integer,
    visit_detail_source_value                               varchar(50),
    visit_detail_source_concept_id                            integer,
    admitted_from_concept_id                                    integer,
    admitted_from_source_value                                    varchar(50),
    discharged_to_source_value                                      varchar(50),
    discharged_to_concept_id                                          integer,
    preceding_visit_detail_id                                           integer,
    parent_visit_detail_id                                                integer,
    visit_occurrence_id                                                     integer     not null
);

create table condition_occurrence (
    condition_occurrence_id              integer     not null,
    person_id                              integer     not null,
    condition_concept_id                     integer     not null,
    condition_start_date                       date        not null,
    condition_start_datetime                     timestamp,
    condition_end_date                             date,
    condition_end_datetime                           timestamp,
    condition_type_concept_id                          integer     not null,
    condition_status_concept_id                          integer,
    stop_reason                                            varchar(20),
    provider_id                                              integer,
    visit_occurrence_id                                        integer,
    visit_detail_id                                              integer,
    condition_source_value                                         varchar(50),
    condition_source_concept_id                                      integer,
    condition_status_source_value                                      varchar(50)
);

create table drug_exposure (
    drug_exposure_id                 integer     not null,
    person_id                          integer     not null,
    drug_concept_id                      integer     not null,
    drug_exposure_start_date               date        not null,
    drug_exposure_start_datetime             timestamp,
    drug_exposure_end_date                     date        not null,
    drug_exposure_end_datetime                   timestamp,
    verbatim_end_date                              date,
    drug_type_concept_id                             integer     not null,
    stop_reason                                        varchar(20),
    refills                                              integer,
    quantity                                               numeric,
    days_supply                                              integer,
    sig                                                        text,
    route_concept_id                                             integer,
    lot_number                                                     varchar(50),
    provider_id                                                      integer,
    visit_occurrence_id                                                integer,
    visit_detail_id                                                      integer,
    drug_source_value                                                      varchar(50),
    drug_source_concept_id                                                   integer,
    route_source_value                                                         varchar(50),
    dose_unit_source_value                                                       varchar(50)
);

create table procedure_occurrence (
    procedure_occurrence_id             integer     not null,
    person_id                             integer     not null,
    procedure_concept_id                    integer     not null,
    procedure_date                            date        not null,
    procedure_datetime                          timestamp,
    procedure_end_date                            date,
    procedure_end_datetime                          timestamp,
    procedure_type_concept_id                         integer     not null,
    modifier_concept_id                                 integer,
    quantity                                              integer,
    provider_id                                             integer,
    visit_occurrence_id                                       integer,
    visit_detail_id                                             integer,
    procedure_source_value                                        varchar(50),
    procedure_source_concept_id                                     integer,
    modifier_source_value                                             varchar(50)
);

create table device_exposure (
    device_exposure_id                   integer     not null,
    person_id                              integer     not null,
    device_concept_id                        integer     not null,
    device_exposure_start_date                 date        not null,
    device_exposure_start_datetime               timestamp,
    device_exposure_end_date                       date,
    device_exposure_end_datetime                     timestamp,
    device_type_concept_id                             integer     not null,
    unique_device_id                                     varchar(255),
    production_id                                          varchar(255),
    quantity                                                 integer,
    provider_id                                                integer,
    visit_occurrence_id                                          integer,
    visit_detail_id                                                integer,
    device_source_value                                              varchar(50),
    device_source_concept_id                                           integer,
    unit_concept_id                                                      integer,
    unit_source_value                                                      varchar(50),
    unit_source_concept_id                                                   integer
);

create table measurement (
    measurement_id                     integer     not null,
    person_id                            integer     not null,
    measurement_concept_id                 integer     not null,
    measurement_date                         date        not null,
    measurement_datetime                       timestamp,
    measurement_time                             varchar(10),
    measurement_type_concept_id                    integer     not null,
    operator_concept_id                              integer,
    value_as_number                                    numeric,
    value_as_concept_id                                  integer,
    unit_concept_id                                        integer,
    range_low                                                numeric,
    range_high                                                 numeric,
    provider_id                                                  integer,
    visit_occurrence_id                                            integer,
    visit_detail_id                                                  integer,
    measurement_source_value                                           varchar(50),
    measurement_source_concept_id                                        integer,
    unit_source_value                                                      varchar(50),
    unit_source_concept_id                                                   integer,
    value_source_value                                                         varchar(50),
    measurement_event_id                                                         bigint,
    meas_event_field_concept_id                                                    integer
);

create table observation (
    observation_id                     integer     not null,
    person_id                            integer     not null,
    observation_concept_id                 integer     not null,
    observation_date                         date        not null,
    observation_datetime                       timestamp,
    observation_type_concept_id                  integer     not null,
    value_as_number                                numeric,
    value_as_string                                  varchar(60),
    value_as_concept_id                                integer,
    qualifier_concept_id                                 integer,
    unit_concept_id                                        integer,
    provider_id                                              integer,
    visit_occurrence_id                                        integer,
    visit_detail_id                                              integer,
    observation_source_value                                       varchar(50),
    observation_source_concept_id                                    integer,
    unit_source_value                                                  varchar(50),
    qualifier_source_value                                               varchar(50),
    value_source_value                                                     varchar(50),
    observation_event_id                                                     bigint,
    obs_event_field_concept_id                                                 integer
);

create table death (
    person_id                integer     not null,
    death_date                  date        not null,
    death_datetime                timestamp,
    death_type_concept_id           integer,
    cause_concept_id                  integer,
    cause_source_value                  varchar(50),
    cause_source_concept_id               integer
);

create table note (
    note_id                       integer         not null,
    person_id                       integer         not null,
    note_date                         date            not null,
    note_datetime                       timestamp,
    note_type_concept_id                  integer         not null,
    note_class_concept_id                   integer         not null,
    note_title                                varchar(250),
    note_text                                   text            not null,
    encoding_concept_id                           integer         not null,
    language_concept_id                             integer         not null,
    provider_id                                       integer,
    visit_occurrence_id                                 integer,
    visit_detail_id                                       integer,
    note_source_value                                       varchar(50),
    note_event_id                                             bigint,
    note_event_field_concept_id                                 integer
);

create table note_nlp (
    note_nlp_id                 integer         not null,
    note_id                       integer         not null,
    section_concept_id              integer,
    snippet                            varchar(250),
    "offset"                            varchar(50),
    lexical_variant                       varchar(250)    not null,
    note_nlp_concept_id                     integer,
    note_nlp_source_concept_id                integer,
    nlp_system                                  varchar(250),
    nlp_date                                      date            not null,
    nlp_datetime                                    timestamp,
    term_exists                                       varchar(1),
    term_temporal                                       varchar(50),
    term_modifiers                                        varchar(2000)
);

create table specimen (
    specimen_id                     integer     not null,
    person_id                         integer     not null,
    specimen_concept_id                 integer     not null,
    specimen_type_concept_id              integer     not null,
    specimen_date                           date        not null,
    specimen_datetime                         timestamp,
    quantity                                    numeric,
    unit_concept_id                               integer,
    anatomic_site_concept_id                        integer,
    disease_status_concept_id                         integer,
    specimen_source_id                                  varchar(50),
    specimen_source_value                                 varchar(50),
    unit_source_value                                       varchar(50),
    anatomic_site_source_value                                varchar(50),
    disease_status_source_value                                 varchar(50)
);

create table fact_relationship (
    domain_concept_id_1        integer     not null,
    fact_id_1                    integer     not null,
    domain_concept_id_2            integer     not null,
    fact_id_2                        integer     not null,
    relationship_concept_id            integer     not null
);

-- ============================================================================
-- Standardized health system data
-- ============================================================================

create table location (
    location_id                integer         not null,
    address_1                     varchar(50),
    address_2                       varchar(50),
    city                               varchar(50),
    state                                varchar(2),
    zip                                    varchar(9),
    county                                    varchar(20),
    location_source_value                      varchar(50),
    country_concept_id                            integer,
    country_source_value                            varchar(80),
    latitude                                          numeric,
    longitude                                           numeric
);

create table care_site (
    care_site_id                    integer     not null,
    care_site_name                    varchar(255),
    place_of_service_concept_id         integer,
    location_id                           integer,
    care_site_source_value                  varchar(50),
    place_of_service_source_value             varchar(50)
);

create table provider (
    provider_id                       integer         not null,
    provider_name                       varchar(255),
    npi                                   varchar(20),
    dea                                     varchar(20),
    specialty_concept_id                      integer,
    care_site_id                                integer,
    year_of_birth                                 integer,
    gender_concept_id                               integer,
    provider_source_value                             varchar(50),
    specialty_source_value                              varchar(50),
    specialty_source_concept_id                           integer,
    gender_source_value                                     varchar(50),
    gender_source_concept_id                                  integer
);

-- ============================================================================
-- Standardized health economics
-- ============================================================================

create table payer_plan_period (
    payer_plan_period_id                  integer     not null,
    person_id                               integer     not null,
    payer_plan_period_start_date              date        not null,
    payer_plan_period_end_date                  date        not null,
    payer_concept_id                              integer,
    payer_source_value                              varchar(50),
    payer_source_concept_id                           integer,
    plan_concept_id                                     integer,
    plan_source_value                                     varchar(50),
    plan_source_concept_id                                  integer,
    sponsor_concept_id                                        integer,
    sponsor_source_value                                        varchar(50),
    sponsor_source_concept_id                                     integer,
    family_source_value                                             varchar(50),
    stop_reason_concept_id                                            integer,
    stop_reason_source_value                                            varchar(50),
    stop_reason_source_concept_id                                         integer
);

create table cost (
    cost_id                          integer         not null,
    cost_event_id                       integer         not null,
    cost_domain_id                        varchar(20)     not null,
    cost_type_concept_id                    integer         not null,
    currency_concept_id                       integer,
    total_charge                                numeric,
    total_cost                                    numeric,
    total_paid                                      numeric,
    paid_by_payer                                     numeric,
    paid_by_patient                                     numeric,
    paid_patient_copay                                    numeric,
    paid_patient_coinsurance                                numeric,
    paid_patient_deductible                                   numeric,
    paid_by_primary                                             numeric,
    paid_ingredient_cost                                          numeric,
    paid_dispensing_fee                                             numeric,
    payer_plan_period_id                                              integer,
    amount_allowed                                                      numeric,
    revenue_code_concept_id                                               integer,
    revenue_code_source_value                                               varchar(50),
    drg_concept_id                                                            integer,
    drg_source_value                                                            varchar(3)
);

-- ============================================================================
-- Standardized derived elements
-- ============================================================================

create table drug_era (
    drug_era_id                integer     not null,
    person_id                    integer     not null,
    drug_concept_id                integer     not null,
    drug_era_start_date              date        not null,
    drug_era_end_date                  date        not null,
    drug_exposure_count                  integer,
    gap_days                               integer
);

create table dose_era (
    dose_era_id             integer     not null,
    person_id                 integer     not null,
    drug_concept_id             integer     not null,
    unit_concept_id               integer     not null,
    dose_value                      numeric     not null,
    dose_era_start_date               date        not null,
    dose_era_end_date                   date        not null
);

create table condition_era (
    condition_era_id                integer     not null,
    person_id                         integer     not null,
    condition_concept_id                integer     not null,
    condition_era_start_date              date        not null,
    condition_era_end_date                  date        not null,
    condition_occurrence_count                integer
);

-- ============================================================================
-- Cohort tables
-- ============================================================================

create table cohort_definition (
    cohort_definition_id                integer         not null,
    cohort_definition_name                varchar(255)    not null,
    cohort_definition_description           text,
    definition_type_concept_id                integer         not null,
    cohort_definition_syntax                    text,
    subject_concept_id                            integer         not null,
    cohort_initiation_date                          date
);

create table cohort (
    cohort_definition_id       integer     not null,
    subject_id                    integer     not null,
    cohort_start_date               date        not null,
    cohort_end_date                   date        not null
);

-- ============================================================================
-- Metadata
-- ============================================================================

create table cdm_source (
    cdm_source_name                     varchar(255)    not null,
    cdm_source_abbreviation               varchar(25),
    cdm_holder                              varchar(255),
    source_description                        text,
    source_documentation_reference              varchar(255),
    cdm_etl_reference                             varchar(255),
    source_release_date                             date,
    cdm_release_date                                  date,
    cdm_version                                         varchar(10),
    cdm_version_concept_id                                integer         not null,
    vocabulary_version                                      varchar(20)
);

create table metadata (
    metadata_id                integer         not null,
    metadata_concept_id           integer         not null,
    metadata_type_concept_id        integer         not null,
    name                               varchar(250)    not null,
    value_as_string                     varchar(250),
    value_as_concept_id                   integer,
    value_as_number                         numeric,
    metadata_date                             date,
    metadata_datetime                           timestamp
);
