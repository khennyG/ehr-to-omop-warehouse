-- OMOP CDM v5.4 — primary keys.
--
-- OHDSI's own reference DDL deliberately leaves several vocabulary and
-- relationship tables without a primary key, because those tables are bulk-loaded
-- from Athena exports where enforcing a key during load costs more than it buys.
-- This project loads a small demo vocabulary, not a multi-gigabyte Athena export, so
-- the trade-off runs the other way: a primary key on concept_relationship,
-- concept_ancestor, drug_strength, and cohort catches a real class of bug (a
-- duplicate "Maps to" row silently doubling a concept's mapped rate) that would
-- otherwise only surface downstream in the DQD coverage numbers. concept_synonym,
-- source_to_concept_map, and fact_relationship keep the upstream convention of no
-- key, since none of their natural key candidates are reliably unique.

set search_path to cdm;

alter table person                 add constraint person_pk                 primary key (person_id);
alter table observation_period     add constraint observation_period_pk     primary key (observation_period_id);
alter table visit_occurrence       add constraint visit_occurrence_pk       primary key (visit_occurrence_id);
alter table visit_detail           add constraint visit_detail_pk           primary key (visit_detail_id);
alter table condition_occurrence   add constraint condition_occurrence_pk   primary key (condition_occurrence_id);
alter table drug_exposure          add constraint drug_exposure_pk          primary key (drug_exposure_id);
alter table procedure_occurrence   add constraint procedure_occurrence_pk   primary key (procedure_occurrence_id);
alter table device_exposure        add constraint device_exposure_pk        primary key (device_exposure_id);
alter table measurement            add constraint measurement_pk            primary key (measurement_id);
alter table observation            add constraint observation_pk            primary key (observation_id);
alter table death                  add constraint death_pk                  primary key (person_id);
alter table note                   add constraint note_pk                   primary key (note_id);
alter table note_nlp               add constraint note_nlp_pk               primary key (note_nlp_id);
alter table specimen               add constraint specimen_pk               primary key (specimen_id);

alter table location                add constraint location_pk                primary key (location_id);
alter table care_site                add constraint care_site_pk                primary key (care_site_id);
alter table provider                  add constraint provider_pk                  primary key (provider_id);

alter table payer_plan_period          add constraint payer_plan_period_pk          primary key (payer_plan_period_id);
alter table cost                        add constraint cost_pk                        primary key (cost_id);

alter table drug_era               add constraint drug_era_pk               primary key (drug_era_id);
alter table dose_era                add constraint dose_era_pk                primary key (dose_era_id);
alter table condition_era            add constraint condition_era_pk            primary key (condition_era_id);

alter table cohort_definition        add constraint cohort_definition_pk        primary key (cohort_definition_id);
alter table cohort                    add constraint cohort_pk                    primary key (cohort_definition_id, subject_id, cohort_start_date);

alter table concept                  add constraint concept_pk                  primary key (concept_id);
alter table vocabulary                add constraint vocabulary_pk                primary key (vocabulary_id);
alter table domain                     add constraint domain_pk                     primary key (domain_id);
alter table concept_class               add constraint concept_class_pk               primary key (concept_class_id);
alter table relationship                 add constraint relationship_pk                 primary key (relationship_id);
alter table concept_relationship          add constraint concept_relationship_pk          primary key (concept_id_1, concept_id_2, relationship_id);
alter table concept_ancestor               add constraint concept_ancestor_pk               primary key (ancestor_concept_id, descendant_concept_id);
alter table drug_strength                   add constraint drug_strength_pk                   primary key (drug_concept_id, ingredient_concept_id);

alter table metadata                add constraint metadata_pk                primary key (metadata_id);
