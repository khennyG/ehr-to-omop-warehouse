"""Tests for the cohort builder's three execution shapes.

Runs against a real, temporary DuckDB file — same reasoning as
tests/test_warehouse_loader.py: this module's SQL is meant to run unchanged
against DuckDB and Postgres, so a mocked connection wouldn't actually verify
that. The fixture builds just enough of person / condition_occurrence /
drug_exposure by hand to exercise each temporal pattern deliberately,
including the cases that should NOT match.
"""

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from src.analytics.cohort_builder import CohortBuilder


@pytest.fixture
def engine(tmp_path):
    engine = create_engine(f"duckdb:///{tmp_path / 'cohort_test.duckdb'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA cdm"))
        conn.execute(text(
            "CREATE TABLE cdm.person (person_id INTEGER, year_of_birth INTEGER)"
        ))
        conn.execute(text(
            "CREATE TABLE cdm.concept ("
            "  concept_id INTEGER, concept_name VARCHAR, domain_id VARCHAR, standard_concept VARCHAR"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE cdm.condition_occurrence ("
            "  person_id INTEGER, condition_concept_id INTEGER, condition_start_date DATE"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE cdm.drug_exposure ("
            "  person_id INTEGER, drug_concept_id INTEGER,"
            "  drug_exposure_start_date DATE, drug_exposure_end_date DATE"
            ")"
        ))
    return engine


def _insert(engine, table, rows):
    if not rows:
        return
    df = pd.DataFrame(rows)
    df.to_sql(table.split(".")[-1], engine, schema=table.split(".")[0], if_exists="append", index=False)


@pytest.fixture
def builder(engine):
    return CohortBuilder(database_url=str(engine.url), schema="cdm")


class TestExecuteConditionToCondition:
    """diabetes_complications is condition -> condition, not drug -> condition —
    this is exactly the case the domain-agnostic rewrite of execute() exists for."""

    @pytest.fixture(autouse=True)
    def seed(self, engine):
        _insert(engine, "cdm.person", [
            {"person_id": 1, "year_of_birth": 1960},
            {"person_id": 2, "year_of_birth": 1960},
            {"person_id": 3, "year_of_birth": 1960},
        ])
        _insert(engine, "cdm.concept", [
            {"concept_id": 100, "concept_name": "Type 2 diabetes mellitus", "domain_id": "Condition", "standard_concept": "S"},
            {"concept_id": 200, "concept_name": "Myocardial infarction", "domain_id": "Condition", "standard_concept": "S"},
        ])
        _insert(engine, "cdm.condition_occurrence", [
            # p1: diabetes then MI 30 days later — inside a 365-day window
            {"person_id": 1, "condition_concept_id": 100, "condition_start_date": "2020-01-01"},
            {"person_id": 1, "condition_concept_id": 200, "condition_start_date": "2020-01-31"},
            # p2: diabetes then MI 400 days later — outside a 365-day window
            {"person_id": 2, "condition_concept_id": 100, "condition_start_date": "2020-01-01"},
            {"person_id": 2, "condition_concept_id": 200, "condition_start_date": "2021-02-05"},
            # p3: diabetes, no MI at all
            {"person_id": 3, "condition_concept_id": 100, "condition_start_date": "2020-01-01"},
        ])

    def test_matches_only_the_in_window_patient(self, builder):
        defn = builder.define(
            name="diabetes_mi", index_domain="Condition", index_terms=["diabetes"],
            outcome_domain="Condition", outcome_terms=["myocardial infarction"],
            temporal_window_days=365,
        )
        result = builder.execute(defn)
        assert result.members["person_id"].tolist() == [1]
        assert result.total_count == 1

    def test_attrition_steps_are_monotonically_decreasing(self, builder):
        defn = builder.define(
            name="diabetes_mi", index_domain="Condition", index_terms=["diabetes"],
            outcome_domain="Condition", outcome_terms=["myocardial infarction"],
            temporal_window_days=365,
        )
        result = builder.execute(defn)
        counts = [step["count"] for step in result.attrition]
        assert counts == sorted(counts, reverse=True)


class TestExecuteEscalation:
    @pytest.fixture(autouse=True)
    def seed(self, engine):
        _insert(engine, "cdm.person", [{"person_id": p, "year_of_birth": 1960} for p in (1, 2, 3)])
        _insert(engine, "cdm.concept", [
            {"concept_id": 10, "concept_name": "Codeine", "domain_id": "Drug", "standard_concept": "S"},
            {"concept_id": 20, "concept_name": "Oxycodone", "domain_id": "Drug", "standard_concept": "S"},
        ])
        _insert(engine, "cdm.drug_exposure", [
            # p1: codeine then oxycodone 30 days later — escalates within 180 days
            {"person_id": 1, "drug_concept_id": 10, "drug_exposure_start_date": "2020-01-01", "drug_exposure_end_date": "2020-01-10"},
            {"person_id": 1, "drug_concept_id": 20, "drug_exposure_start_date": "2020-01-31", "drug_exposure_end_date": "2020-02-10"},
            # p2: codeine only — never escalates
            {"person_id": 2, "drug_concept_id": 10, "drug_exposure_start_date": "2020-01-01", "drug_exposure_end_date": "2020-01-10"},
            # p3: codeine then oxycodone 300 days later — outside a 180-day window
            {"person_id": 3, "drug_concept_id": 10, "drug_exposure_start_date": "2020-01-01", "drug_exposure_end_date": "2020-01-10"},
            {"person_id": 3, "drug_concept_id": 20, "drug_exposure_start_date": "2020-10-28", "drug_exposure_end_date": "2020-11-05"},
        ])

    def test_matches_only_the_escalated_patient(self, builder):
        result = builder.execute_escalation(
            name="opioid_escalation", drug_ladder_terms=["codeine", "oxycodone"], window_days=180,
        )
        assert result.members["person_id"].tolist() == [1]


class TestExecuteConcurrentDrugCount:
    @pytest.fixture(autouse=True)
    def seed(self, engine):
        _insert(engine, "cdm.person", [
            {"person_id": 1, "year_of_birth": 1950},  # 65+ in most reference years
            {"person_id": 2, "year_of_birth": 1950},
        ])
        _insert(engine, "cdm.drug_exposure", [
            # p1: three drugs all overlapping January 2020 — peak concurrency 3
            {"person_id": 1, "drug_concept_id": 1, "drug_exposure_start_date": "2020-01-01", "drug_exposure_end_date": "2020-02-01"},
            {"person_id": 1, "drug_concept_id": 2, "drug_exposure_start_date": "2020-01-10", "drug_exposure_end_date": "2020-02-10"},
            {"person_id": 1, "drug_concept_id": 3, "drug_exposure_start_date": "2020-01-15", "drug_exposure_end_date": "2020-02-15"},
            # p2: three drugs, but strictly sequential — peak concurrency 1
            {"person_id": 2, "drug_concept_id": 1, "drug_exposure_start_date": "2020-01-01", "drug_exposure_end_date": "2020-01-31"},
            {"person_id": 2, "drug_concept_id": 2, "drug_exposure_start_date": "2020-02-01", "drug_exposure_end_date": "2020-02-28"},
            {"person_id": 2, "drug_concept_id": 3, "drug_exposure_start_date": "2020-03-01", "drug_exposure_end_date": "2020-03-31"},
        ])

    def test_matches_only_the_overlapping_patient(self, builder):
        result = builder.execute_concurrent_drug_count(name="polypharmacy", min_concurrent_drugs=3)
        assert result.members["person_id"].tolist() == [1]

    def test_sequential_drugs_never_count_as_concurrent(self, builder):
        result = builder.execute_concurrent_drug_count(name="polypharmacy", min_concurrent_drugs=2)
        assert 2 not in result.members["person_id"].tolist()

    def test_age_filter_applies_on_top(self, builder):
        result = builder.execute_concurrent_drug_count(name="polypharmacy", min_concurrent_drugs=3, min_age=200)
        assert result.total_count == 0
