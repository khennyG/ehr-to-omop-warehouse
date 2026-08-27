-- OMOP CDM v5.4 — foreign keys.
--
-- Two families of reference dominate this file: every clinical event points back to
-- person_id, and every *_concept_id column points at concept.concept_id. The second
-- one is what makes DQD's check_concept_valid meaningful — it's an actual constraint
-- the database enforces, not just a convention the ETL is supposed to honor. That
-- only works because concept_id = 0 ("No matching concept") is seeded as a real row
-- in the concept table before any clinical data loads; see
-- scripts/build_demo_vocabulary.py. Loading order matters here: vocabulary tables
-- and person before everything else, which is exactly the order
-- src/load/warehouse_loader.py already loads in.

set search_path to cdm;

-- ── Vocabulary internal references ──────────────────────────────────────────

alter table concept                add constraint concept_domain_fk                foreign key (domain_id) references domain (domain_id);
alter table concept                add constraint concept_vocabulary_fk            foreign key (vocabulary_id) references vocabulary (vocabulary_id);
alter table concept                add constraint concept_class_fk                 foreign key (concept_class_id) references concept_class (concept_class_id);

-- domain.domain_concept_id, vocabulary.vocabulary_concept_id,
-- concept_class.concept_class_concept_id, and relationship.relationship_concept_id
-- each point back at the concept row that describes the domain/vocabulary/class/
-- relationship itself — but concept.domain_id, concept.vocabulary_id, and
-- concept.concept_class_id point the other way, at domain/vocabulary/concept_class.
-- Enforcing both directions as foreign keys makes the four tables mutually
-- dependent, and there's no load order that satisfies a circular reference on first
-- insert. Real OMOP installs hit this too — it's why bulk vocabulary loads either
-- defer constraint checking or, as here, simply don't enforce the
-- metadata-pointing-back-at-itself direction. The load order this pipeline uses
-- (domain, vocabulary, concept_class, then concept) is the direction that's safe to
-- enforce, so that's the direction that gets a constraint.

alter table concept_relationship   add constraint concept_relationship_c1_fk       foreign key (concept_id_1) references concept (concept_id);
alter table concept_relationship   add constraint concept_relationship_c2_fk       foreign key (concept_id_2) references concept (concept_id);
alter table concept_relationship   add constraint concept_relationship_rel_fk      foreign key (relationship_id) references relationship (relationship_id);

alter table concept_synonym        add constraint concept_synonym_concept_fk       foreign key (concept_id) references concept (concept_id);
alter table concept_synonym        add constraint concept_synonym_lang_fk          foreign key (language_concept_id) references concept (concept_id);

alter table concept_ancestor       add constraint concept_ancestor_anc_fk          foreign key (ancestor_concept_id) references concept (concept_id);
alter table concept_ancestor       add constraint concept_ancestor_desc_fk         foreign key (descendant_concept_id) references concept (concept_id);

alter table drug_strength          add constraint drug_strength_drug_fk            foreign key (drug_concept_id) references concept (concept_id);
alter table drug_strength          add constraint drug_strength_ingredient_fk      foreign key (ingredient_concept_id) references concept (concept_id);
alter table drug_strength          add constraint drug_strength_amount_unit_fk     foreign key (amount_unit_concept_id) references concept (concept_id);
alter table drug_strength          add constraint drug_strength_num_unit_fk        foreign key (numerator_unit_concept_id) references concept (concept_id);
alter table drug_strength          add constraint drug_strength_denom_unit_fk      foreign key (denominator_unit_concept_id) references concept (concept_id);

-- ── Health system ────────────────────────────────────────────────────────────

alter table location               add constraint location_country_fk              foreign key (country_concept_id) references concept (concept_id);

alter table care_site              add constraint care_site_location_fk            foreign key (location_id) references location (location_id);
alter table care_site              add constraint care_site_pos_fk                 foreign key (place_of_service_concept_id) references concept (concept_id);

alter table provider               add constraint provider_care_site_fk            foreign key (care_site_id) references care_site (care_site_id);
alter table provider               add constraint provider_specialty_fk            foreign key (specialty_concept_id) references concept (concept_id);
alter table provider               add constraint provider_gender_fk               foreign key (gender_concept_id) references concept (concept_id);

-- ── Person ────────────────────────────────────────────────────────────────

alter table person                 add constraint person_gender_fk                 foreign key (gender_concept_id) references concept (concept_id);
alter table person                 add constraint person_race_fk                   foreign key (race_concept_id) references concept (concept_id);
alter table person                 add constraint person_ethnicity_fk              foreign key (ethnicity_concept_id) references concept (concept_id);
alter table person                 add constraint person_location_fk               foreign key (location_id) references location (location_id);
alter table person                 add constraint person_provider_fk               foreign key (provider_id) references provider (provider_id);
alter table person                 add constraint person_care_site_fk              foreign key (care_site_id) references care_site (care_site_id);

-- ── Observation period / visits ──────────────────────────────────────────────

alter table observation_period     add constraint obs_period_person_fk             foreign key (person_id) references person (person_id);
alter table observation_period     add constraint obs_period_type_fk               foreign key (period_type_concept_id) references concept (concept_id);

alter table visit_occurrence       add constraint visit_person_fk                  foreign key (person_id) references person (person_id);
alter table visit_occurrence       add constraint visit_concept_fk                 foreign key (visit_concept_id) references concept (concept_id);
alter table visit_occurrence       add constraint visit_type_fk                    foreign key (visit_type_concept_id) references concept (concept_id);
alter table visit_occurrence       add constraint visit_provider_fk                foreign key (provider_id) references provider (provider_id);
alter table visit_occurrence       add constraint visit_care_site_fk               foreign key (care_site_id) references care_site (care_site_id);
alter table visit_occurrence       add constraint visit_preceding_fk               foreign key (preceding_visit_occurrence_id) references visit_occurrence (visit_occurrence_id);

alter table visit_detail           add constraint visit_detail_person_fk           foreign key (person_id) references person (person_id);
alter table visit_detail           add constraint visit_detail_concept_fk          foreign key (visit_detail_concept_id) references concept (concept_id);
alter table visit_detail           add constraint visit_detail_type_fk             foreign key (visit_detail_type_concept_id) references concept (concept_id);
alter table visit_detail           add constraint visit_detail_visit_fk            foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table visit_detail           add constraint visit_detail_preceding_fk        foreign key (preceding_visit_detail_id) references visit_detail (visit_detail_id);
alter table visit_detail           add constraint visit_detail_parent_fk           foreign key (parent_visit_detail_id) references visit_detail (visit_detail_id);

-- ── Clinical events ───────────────────────────────────────────────────────────

alter table condition_occurrence   add constraint condition_person_fk              foreign key (person_id) references person (person_id);
alter table condition_occurrence   add constraint condition_concept_fk             foreign key (condition_concept_id) references concept (concept_id);
alter table condition_occurrence   add constraint condition_type_fk                foreign key (condition_type_concept_id) references concept (concept_id);
alter table condition_occurrence   add constraint condition_status_fk              foreign key (condition_status_concept_id) references concept (concept_id);
alter table condition_occurrence   add constraint condition_visit_fk               foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table condition_occurrence   add constraint condition_visit_detail_fk        foreign key (visit_detail_id) references visit_detail (visit_detail_id);

alter table drug_exposure          add constraint drug_person_fk                   foreign key (person_id) references person (person_id);
alter table drug_exposure          add constraint drug_concept_fk                  foreign key (drug_concept_id) references concept (concept_id);
alter table drug_exposure          add constraint drug_type_fk                     foreign key (drug_type_concept_id) references concept (concept_id);
alter table drug_exposure          add constraint drug_route_fk                    foreign key (route_concept_id) references concept (concept_id);
alter table drug_exposure          add constraint drug_visit_fk                    foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table drug_exposure          add constraint drug_visit_detail_fk             foreign key (visit_detail_id) references visit_detail (visit_detail_id);

alter table procedure_occurrence   add constraint procedure_person_fk              foreign key (person_id) references person (person_id);
alter table procedure_occurrence   add constraint procedure_concept_fk             foreign key (procedure_concept_id) references concept (concept_id);
alter table procedure_occurrence   add constraint procedure_type_fk                foreign key (procedure_type_concept_id) references concept (concept_id);
alter table procedure_occurrence   add constraint procedure_modifier_fk            foreign key (modifier_concept_id) references concept (concept_id);
alter table procedure_occurrence   add constraint procedure_visit_fk               foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table procedure_occurrence   add constraint procedure_visit_detail_fk        foreign key (visit_detail_id) references visit_detail (visit_detail_id);

alter table device_exposure        add constraint device_person_fk                 foreign key (person_id) references person (person_id);
alter table device_exposure        add constraint device_concept_fk                foreign key (device_concept_id) references concept (concept_id);
alter table device_exposure        add constraint device_type_fk                   foreign key (device_type_concept_id) references concept (concept_id);
alter table device_exposure        add constraint device_unit_fk                   foreign key (unit_concept_id) references concept (concept_id);
alter table device_exposure        add constraint device_visit_fk                  foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table device_exposure        add constraint device_visit_detail_fk           foreign key (visit_detail_id) references visit_detail (visit_detail_id);

alter table measurement            add constraint measurement_person_fk            foreign key (person_id) references person (person_id);
alter table measurement            add constraint measurement_concept_fk           foreign key (measurement_concept_id) references concept (concept_id);
alter table measurement            add constraint measurement_type_fk              foreign key (measurement_type_concept_id) references concept (concept_id);
alter table measurement            add constraint measurement_operator_fk          foreign key (operator_concept_id) references concept (concept_id);
alter table measurement            add constraint measurement_value_concept_fk     foreign key (value_as_concept_id) references concept (concept_id);
alter table measurement            add constraint measurement_unit_fk              foreign key (unit_concept_id) references concept (concept_id);
alter table measurement            add constraint measurement_visit_fk             foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table measurement            add constraint measurement_visit_detail_fk      foreign key (visit_detail_id) references visit_detail (visit_detail_id);

alter table observation            add constraint observation_person_fk            foreign key (person_id) references person (person_id);
alter table observation            add constraint observation_concept_fk           foreign key (observation_concept_id) references concept (concept_id);
alter table observation            add constraint observation_type_fk              foreign key (observation_type_concept_id) references concept (concept_id);
alter table observation            add constraint observation_value_concept_fk     foreign key (value_as_concept_id) references concept (concept_id);
alter table observation            add constraint observation_qualifier_fk         foreign key (qualifier_concept_id) references concept (concept_id);
alter table observation            add constraint observation_unit_fk              foreign key (unit_concept_id) references concept (concept_id);
alter table observation            add constraint observation_visit_fk             foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table observation            add constraint observation_visit_detail_fk      foreign key (visit_detail_id) references visit_detail (visit_detail_id);

alter table death                  add constraint death_person_fk                  foreign key (person_id) references person (person_id);
alter table death                  add constraint death_type_fk                    foreign key (death_type_concept_id) references concept (concept_id);
alter table death                  add constraint death_cause_fk                   foreign key (cause_concept_id) references concept (concept_id);

alter table note                   add constraint note_person_fk                   foreign key (person_id) references person (person_id);
alter table note                   add constraint note_type_fk                     foreign key (note_type_concept_id) references concept (concept_id);
alter table note                   add constraint note_class_fk                    foreign key (note_class_concept_id) references concept (concept_id);
alter table note                   add constraint note_encoding_fk                 foreign key (encoding_concept_id) references concept (concept_id);
alter table note                   add constraint note_language_fk                 foreign key (language_concept_id) references concept (concept_id);
alter table note                   add constraint note_visit_fk                    foreign key (visit_occurrence_id) references visit_occurrence (visit_occurrence_id);
alter table note                   add constraint note_visit_detail_fk             foreign key (visit_detail_id) references visit_detail (visit_detail_id);

alter table note_nlp               add constraint note_nlp_note_fk                 foreign key (note_id) references note (note_id);
alter table note_nlp               add constraint note_nlp_section_fk              foreign key (section_concept_id) references concept (concept_id);
alter table note_nlp               add constraint note_nlp_concept_fk              foreign key (note_nlp_concept_id) references concept (concept_id);

alter table specimen               add constraint specimen_person_fk               foreign key (person_id) references person (person_id);
alter table specimen               add constraint specimen_concept_fk              foreign key (specimen_concept_id) references concept (concept_id);
alter table specimen               add constraint specimen_type_fk                 foreign key (specimen_type_concept_id) references concept (concept_id);
alter table specimen               add constraint specimen_unit_fk                 foreign key (unit_concept_id) references concept (concept_id);
alter table specimen               add constraint specimen_anatomic_site_fk        foreign key (anatomic_site_concept_id) references concept (concept_id);
alter table specimen               add constraint specimen_disease_status_fk       foreign key (disease_status_concept_id) references concept (concept_id);

-- fact_relationship deliberately has no foreign keys: fact_id_1/fact_id_2 point at
-- the surrogate key of whatever table domain_concept_id_1/2 names, so the reference
-- target isn't fixed to one table and can't be expressed as a single FK.

-- ── Health economics ──────────────────────────────────────────────────────────

alter table payer_plan_period      add constraint payer_plan_person_fk             foreign key (person_id) references person (person_id);
alter table payer_plan_period      add constraint payer_plan_payer_fk              foreign key (payer_concept_id) references concept (concept_id);
alter table payer_plan_period      add constraint payer_plan_plan_fk               foreign key (plan_concept_id) references concept (concept_id);
alter table payer_plan_period      add constraint payer_plan_sponsor_fk            foreign key (sponsor_concept_id) references concept (concept_id);
alter table payer_plan_period      add constraint payer_plan_stop_reason_fk        foreign key (stop_reason_concept_id) references concept (concept_id);

alter table cost                   add constraint cost_type_fk                     foreign key (cost_type_concept_id) references concept (concept_id);
alter table cost                   add constraint cost_currency_fk                 foreign key (currency_concept_id) references concept (concept_id);
alter table cost                   add constraint cost_payer_plan_fk               foreign key (payer_plan_period_id) references payer_plan_period (payer_plan_period_id);
alter table cost                   add constraint cost_revenue_code_fk             foreign key (revenue_code_concept_id) references concept (concept_id);
alter table cost                   add constraint cost_drg_fk                      foreign key (drg_concept_id) references concept (concept_id);

-- ── Derived elements ──────────────────────────────────────────────────────────

alter table drug_era               add constraint drug_era_person_fk               foreign key (person_id) references person (person_id);
alter table drug_era               add constraint drug_era_concept_fk              foreign key (drug_concept_id) references concept (concept_id);

alter table dose_era               add constraint dose_era_person_fk               foreign key (person_id) references person (person_id);
alter table dose_era               add constraint dose_era_concept_fk              foreign key (drug_concept_id) references concept (concept_id);
alter table dose_era               add constraint dose_era_unit_fk                 foreign key (unit_concept_id) references concept (concept_id);

alter table condition_era          add constraint condition_era_person_fk          foreign key (person_id) references person (person_id);
alter table condition_era          add constraint condition_era_concept_fk         foreign key (condition_concept_id) references concept (concept_id);

-- ── Cohort ────────────────────────────────────────────────────────────────────

alter table cohort_definition      add constraint cohort_def_type_fk               foreign key (definition_type_concept_id) references concept (concept_id);
alter table cohort_definition      add constraint cohort_def_subject_fk            foreign key (subject_concept_id) references concept (concept_id);
alter table cohort                 add constraint cohort_definition_fk             foreign key (cohort_definition_id) references cohort_definition (cohort_definition_id);

-- ── Metadata ──────────────────────────────────────────────────────────────────

alter table cdm_source              add constraint cdm_source_version_fk            foreign key (cdm_version_concept_id) references concept (concept_id);
alter table metadata                add constraint metadata_concept_fk              foreign key (metadata_concept_id) references concept (concept_id);
alter table metadata                add constraint metadata_type_fk                 foreign key (metadata_type_concept_id) references concept (concept_id);
alter table metadata                add constraint metadata_value_concept_fk        foreign key (value_as_concept_id) references concept (concept_id);
