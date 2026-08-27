-- OMOP CDM v5.4 — indices.
--
-- Primary keys already index their own column, so this file only adds indices
-- for columns that get filtered or joined on but aren't part of a key: person_id on
-- every clinical table (nearly every query in cohort_builder.py and dqd_checks.py
-- starts by narrowing to a person or joining back to person), the *_concept_id
-- columns DQD's completeness/conformance checks scan, and concept's natural lookup
-- columns (vocabulary_id + concept_code is exactly how vocabulary_mapper.py resolves
-- a source code, and it does that lookup once per row of every clinical table during
-- transform — an unindexed scan there would be the single slowest thing in the
-- pipeline once the demo data grows past a few thousand patients).

set search_path to cdm;

create index idx_person_id                    on person (person_id);

create index idx_visit_person_id               on visit_occurrence (person_id);
create index idx_visit_concept_id                on visit_occurrence (visit_concept_id);

create index idx_visit_detail_person_id           on visit_detail (person_id);
create index idx_visit_detail_visit_id              on visit_detail (visit_occurrence_id);

create index idx_condition_person_id                 on condition_occurrence (person_id);
create index idx_condition_concept_id                  on condition_occurrence (condition_concept_id);
create index idx_condition_visit_id                      on condition_occurrence (visit_occurrence_id);
create index idx_condition_start_date                      on condition_occurrence (condition_start_date);

create index idx_drug_person_id                               on drug_exposure (person_id);
create index idx_drug_concept_id                                on drug_exposure (drug_concept_id);
create index idx_drug_visit_id                                    on drug_exposure (visit_occurrence_id);
create index idx_drug_start_date                                     on drug_exposure (drug_exposure_start_date);

create index idx_procedure_person_id                                    on procedure_occurrence (person_id);
create index idx_procedure_concept_id                                      on procedure_occurrence (procedure_concept_id);
create index idx_procedure_visit_id                                          on procedure_occurrence (visit_occurrence_id);

create index idx_device_person_id                                              on device_exposure (person_id);
create index idx_device_concept_id                                                on device_exposure (device_concept_id);

create index idx_measurement_person_id                                               on measurement (person_id);
create index idx_measurement_concept_id                                                 on measurement (measurement_concept_id);
create index idx_measurement_visit_id                                                      on measurement (visit_occurrence_id);
create index idx_measurement_date                                                             on measurement (measurement_date);

create index idx_observation_person_id                                                          on observation (person_id);
create index idx_observation_concept_id                                                            on observation (observation_concept_id);
create index idx_observation_visit_id                                                                 on observation (visit_occurrence_id);

create index idx_death_person_id                                                                         on death (person_id);

create index idx_note_person_id                                                                             on note (person_id);
create index idx_note_nlp_note_id                                                                              on note_nlp (note_id);

create index idx_specimen_person_id                                                                               on specimen (person_id);
create index idx_specimen_concept_id                                                                                 on specimen (specimen_concept_id);

create index idx_payer_plan_person_id                                                                                   on payer_plan_period (person_id);
create index idx_cost_event_id                                                                                            on cost (cost_event_id);

create index idx_drug_era_person_id                                                                                          on drug_era (person_id);
create index idx_drug_era_concept_id                                                                                            on drug_era (drug_concept_id);
create index idx_dose_era_person_id                                                                                                on dose_era (person_id);
create index idx_condition_era_person_id                                                                                              on condition_era (person_id);

create index idx_cohort_subject_id                                                                                                       on cohort (subject_id);
create index idx_cohort_definition_id                                                                                                       on cohort (cohort_definition_id);

-- Vocabulary lookups — these carry the pipeline's actual runtime cost, since every
-- source code resolved during transform hits concept once and concept_relationship
-- once (see VocabularyMapper.source_to_concept_id and .to_standard).
create index idx_concept_code                     on concept (vocabulary_id, concept_code);
create index idx_concept_domain                     on concept (domain_id);
create index idx_concept_class                        on concept (concept_class_id);

create index idx_concept_relationship_c1                on concept_relationship (concept_id_1, relationship_id);
create index idx_concept_relationship_c2                   on concept_relationship (concept_id_2, relationship_id);

create index idx_concept_ancestor_ancestor                    on concept_ancestor (ancestor_concept_id);
create index idx_concept_ancestor_descendant                     on concept_ancestor (descendant_concept_id);

create index idx_concept_synonym_id                                  on concept_synonym (concept_id);

create index idx_source_to_concept_map_code                            on source_to_concept_map (source_vocabulary_id, source_code);

create index idx_drug_strength_drug                                       on drug_strength (drug_concept_id);
create index idx_drug_strength_ingredient                                    on drug_strength (ingredient_concept_id);
