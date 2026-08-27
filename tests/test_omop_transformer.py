"""Tests for the OMOP transform functions.

Each test builds a small Synthea-shaped fixture DataFrame directly, in the
same spirit as tests/test_vocabulary_mapper.py's in-memory concept fixture —
no database, no real vocabulary download, just enough rows to exercise the
mapping and filtering logic each transform function is responsible for.
"""

import pandas as pd
import pytest

from src.transform.omop_transformer import (
    transform_condition_occurrence,
    transform_death,
    transform_drug_exposure,
    transform_measurement,
    transform_observation,
    transform_observation_period,
    transform_person,
    transform_procedure_occurrence,
    transform_visit_occurrence,
)
from src.transform.vocabulary_mapper import VocabularyMapper


@pytest.fixture
def mapper(tmp_path):
    """A VocabularyMapper loaded with a handful of SNOMED/RxNorm/LOINC codes,
    including one non-standard code that requires a Maps-to hop."""
    concept_data = pd.DataFrame({
        "concept_id": [44054006, 2000001, 6809, 4548004],
        "concept_name": [
            "Type 2 diabetes mellitus (legacy)", "Type 2 diabetes mellitus",
            "Metformin", "Hemoglobin A1c",
        ],
        "domain_id": ["Condition", "Condition", "Drug", "Measurement"],
        "vocabulary_id": ["SNOMED", "SNOMED", "RxNorm", "LOINC"],
        "concept_class_id": ["Clinical Finding"] * 4,
        "standard_concept": [None, "S", "S", "S"],
        "concept_code": ["44054006", "201826", "6809", "4548-4"],
    })
    relationship_data = pd.DataFrame({
        "concept_id_1": [44054006],
        "concept_id_2": [2000001],
        "relationship_id": ["Maps to"],
    })
    concept_data.to_csv(tmp_path / "CONCEPT.csv", sep="\t", index=False)
    relationship_data.to_csv(tmp_path / "CONCEPT_RELATIONSHIP.csv", sep="\t", index=False)

    m = VocabularyMapper(vocab_dir=tmp_path)
    m.load()
    return m


@pytest.fixture
def stg_patients():
    return pd.DataFrame({
        "Id": ["p1", "p2", "p3"],
        "BIRTHDATE": ["1950-03-14", "1990-07-22", "2001-01-01"],
        "DEATHDATE": ["2022-11-02", None, None],
        "GENDER": ["M", "F", "F"],
        "RACE": ["white", "black", "asian"],
        "ETHNICITY": ["nonhispanic", "hispanic", "nonhispanic"],
    })


class TestTransformPerson:
    def test_maps_gender_race_ethnicity(self, stg_patients, mapper):
        person = transform_person(stg_patients, mapper)
        assert person.loc[0, "gender_concept_id"] == 8507  # Male
        assert person.loc[1, "gender_concept_id"] == 8532  # Female
        assert person.loc[0, "race_concept_id"] == 8527  # White
        assert person.loc[1, "ethnicity_concept_id"] == 38003563  # Hispanic

    def test_unmapped_values_fall_back_to_zero(self, mapper):
        df = pd.DataFrame({
            "Id": ["p1"], "BIRTHDATE": ["2000-01-01"], "DEATHDATE": [None],
            "GENDER": ["X"], "RACE": ["unknown"], "ETHNICITY": ["unknown"],
        })
        person = transform_person(df, mapper)
        assert person.loc[0, "gender_concept_id"] == 0
        assert person.loc[0, "race_concept_id"] == 0

    def test_birth_date_components(self, stg_patients, mapper):
        person = transform_person(stg_patients, mapper)
        assert person.loc[0, "year_of_birth"] == 1950
        assert person.loc[0, "month_of_birth"] == 3
        assert person.loc[0, "day_of_birth"] == 14

    def test_sequential_ids(self, stg_patients, mapper):
        person = transform_person(stg_patients, mapper)
        assert person["person_id"].tolist() == [1, 2, 3]


class TestTransformVisitOccurrence:
    def test_maps_encounter_class_and_person(self, mapper):
        encounters = pd.DataFrame({
            "Id": ["e1", "e2"],
            "PATIENT": ["p1", "p2"],
            "ENCOUNTERCLASS": ["ambulatory", "inpatient"],
            "START": ["2021-01-01", "2021-06-15"],
            "STOP": ["2021-01-01", "2021-06-16"],
        })
        person_lookup = {"p1": 1, "p2": 2}
        visits = transform_visit_occurrence(encounters, person_lookup, mapper)
        assert visits.loc[0, "visit_concept_id"] == 9202  # Outpatient
        assert visits.loc[1, "visit_concept_id"] == 9201  # Inpatient
        assert visits["visit_occurrence_id"].tolist() == [1, 2]

    def test_drops_unmapped_patients(self, mapper):
        encounters = pd.DataFrame({
            "Id": ["e1"], "PATIENT": ["ghost"], "ENCOUNTERCLASS": ["ambulatory"],
            "START": ["2021-01-01"], "STOP": ["2021-01-01"],
        })
        visits = transform_visit_occurrence(encounters, {"p1": 1}, mapper)
        assert len(visits) == 0


class TestTransformConditionOccurrence:
    def test_resolves_snomed_and_maps_to_standard(self, mapper):
        conditions = pd.DataFrame({
            "START": ["2020-05-01"], "STOP": [None], "PATIENT": ["p1"],
            "ENCOUNTER": ["e1"], "CODE": ["44054006"], "DESCRIPTION": ["Diabetes"],
        })
        result = transform_condition_occurrence(
            conditions, {"p1": 1}, {"e1": 1}, mapper
        )
        # 44054006 is a non-standard source concept that maps to 2000001
        assert result.loc[0, "condition_source_concept_id"] == 44054006
        assert result.loc[0, "condition_concept_id"] == 2000001

    def test_unmapped_code_falls_back_to_zero(self, mapper):
        conditions = pd.DataFrame({
            "START": ["2020-05-01"], "STOP": [None], "PATIENT": ["p1"],
            "ENCOUNTER": ["e1"], "CODE": ["99999999"], "DESCRIPTION": ["Unknown"],
        })
        result = transform_condition_occurrence(conditions, {"p1": 1}, {"e1": 1}, mapper)
        assert result.loc[0, "condition_concept_id"] == 0


class TestTransformDrugExposure:
    def test_resolves_rxnorm(self, mapper):
        meds = pd.DataFrame({
            "START": ["2020-05-01"], "STOP": ["2020-06-01"], "PATIENT": ["p1"],
            "ENCOUNTER": ["e1"], "CODE": ["6809"], "DESCRIPTION": ["Metformin"],
            "DISPENSES": [3],
        })
        result = transform_drug_exposure(meds, {"p1": 1}, {"e1": 1}, mapper)
        assert result.loc[0, "drug_concept_id"] == 6809


class TestTransformMeasurementAndObservation:
    @pytest.fixture
    def observations(self):
        return pd.DataFrame({
            "DATE": ["2021-02-01", "2021-02-01"],
            "PATIENT": ["p1", "p1"],
            "ENCOUNTER": ["e1", "e1"],
            "CATEGORY": ["laboratory", "social-history"],
            "CODE": ["4548-4", "72166-2"],
            "DESCRIPTION": ["Hemoglobin A1c", "Tobacco smoking status"],
            "VALUE": ["7.2", "Never smoker"],
            "UNITS": ["%", ""],
            "TYPE": ["numeric", "text"],
        })

    def test_measurement_keeps_only_numeric(self, observations, mapper):
        measurements = transform_measurement(observations, {"p1": 1}, {"e1": 1}, mapper)
        assert len(measurements) == 1
        assert measurements.loc[0, "value_as_number"] == 7.2
        assert measurements.loc[0, "measurement_concept_id"] == 4548004

    def test_observation_keeps_only_non_numeric(self, observations, mapper):
        obs = transform_observation(observations, {"p1": 1}, {"e1": 1}, mapper)
        assert len(obs) == 1
        assert obs.loc[0, "value_as_string"] == "Never smoker"


class TestTransformProcedureOccurrence:
    def test_resolves_snomed_procedure(self, mapper):
        procedures = pd.DataFrame({
            "START": ["2021-03-01"], "STOP": ["2021-03-01"], "PATIENT": ["p1"],
            "ENCOUNTER": ["e1"], "CODE": ["44054006"], "DESCRIPTION": ["Placeholder procedure"],
        })
        result = transform_procedure_occurrence(procedures, {"p1": 1}, {"e1": 1}, mapper)
        assert result.loc[0, "procedure_concept_id"] == 2000001


class TestTransformDeath:
    def test_only_deceased_patients_included(self, stg_patients, mapper):
        death = transform_death(stg_patients, {"p1": 1, "p2": 2, "p3": 3})
        assert len(death) == 1
        assert death.loc[0, "person_id"] == 1


class TestTransformObservationPeriod:
    def test_derives_span_per_person(self):
        visits = pd.DataFrame({
            "person_id": [1, 1, 2],
            "visit_start_date": pd.to_datetime(["2019-01-01", "2020-06-01", "2021-01-01"]).date,
            "visit_end_date": pd.to_datetime(["2019-01-01", "2020-06-02", "2021-01-02"]).date,
        })
        periods = transform_observation_period(visits)
        person_1 = periods[periods["person_id"] == 1].iloc[0]
        assert str(person_1["observation_period_start_date"]) == "2019-01-01"
        assert str(person_1["observation_period_end_date"]) == "2020-06-02"
