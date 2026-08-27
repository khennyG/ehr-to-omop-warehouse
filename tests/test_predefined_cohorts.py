"""Smoke tests for the predefined cohort catalog.

The temporal logic itself is covered by tests/test_cohort_builder.py — this
just confirms the three concrete definitions wire real parameters onto that
engine without error and return the shape the rest of the analytics layer
(and the notebooks) expect.
"""

import pytest
from sqlalchemy import create_engine, text

from src.analytics.cohort_builder import CohortBuilder, CohortResult
from src.analytics.predefined_cohorts import (
    PREDEFINED_COHORTS,
    diabetes_complications,
    opioid_escalation,
    polypharmacy_elderly,
    run_all,
)


@pytest.fixture
def builder(tmp_path):
    engine = create_engine(f"duckdb:///{tmp_path / 'predefined_test.duckdb'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA cdm"))
        conn.execute(text("CREATE TABLE cdm.person (person_id INTEGER, year_of_birth INTEGER)"))
        conn.execute(text(
            "CREATE TABLE cdm.concept (concept_id INTEGER, concept_name VARCHAR, domain_id VARCHAR, standard_concept VARCHAR)"
        ))
        conn.execute(text(
            "CREATE TABLE cdm.condition_occurrence (person_id INTEGER, condition_concept_id INTEGER, condition_start_date DATE)"
        ))
        conn.execute(text(
            "CREATE TABLE cdm.drug_exposure (person_id INTEGER, drug_concept_id INTEGER, "
            "drug_exposure_start_date DATE, drug_exposure_end_date DATE)"
        ))
        conn.execute(text(
            "INSERT INTO cdm.person VALUES (1, 1950), (2, 1990)"
        ))
        conn.execute(text(
            "INSERT INTO cdm.concept VALUES "
            "(100, 'Type 2 diabetes mellitus', 'Condition', 'S'), "
            "(200, 'Myocardial infarction', 'Condition', 'S'), "
            "(10, 'Codeine', 'Drug', 'S'), (20, 'Hydrocodone', 'Drug', 'S')"
        ))
        conn.execute(text(
            "INSERT INTO cdm.condition_occurrence VALUES "
            "(1, 100, '2020-01-01'), (1, 200, '2020-03-01')"
        ))
        conn.execute(text(
            "INSERT INTO cdm.drug_exposure VALUES "
            "(1, 10, '2020-01-01', '2020-01-10'), (1, 20, '2020-01-20', '2020-01-30')"
        ))
    return CohortBuilder(database_url=str(engine.url), schema="cdm")


class TestPredefinedCohorts:
    def test_diabetes_complications_returns_cohort_result(self, builder):
        result = diabetes_complications(builder)
        assert isinstance(result, CohortResult)
        assert result.definition.name == "diabetes_complications"

    def test_opioid_escalation_returns_cohort_result(self, builder):
        result = opioid_escalation(builder)
        assert isinstance(result, CohortResult)
        assert 1 in result.members["person_id"].tolist()

    def test_polypharmacy_elderly_returns_cohort_result(self, builder):
        result = polypharmacy_elderly(builder)
        assert isinstance(result, CohortResult)

    def test_run_all_returns_all_three_by_name(self, builder):
        results = run_all(builder)
        assert set(results.keys()) == set(PREDEFINED_COHORTS.keys())
        assert all(isinstance(r, CohortResult) for r in results.values())
