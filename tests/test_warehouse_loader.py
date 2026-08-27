"""Tests for the warehouse loader.

These run against a real, temporary DuckDB file rather than a mocked
connection — the point of the dual-backend design in src/config/settings.py is
that this module's SQL runs unchanged against DuckDB and Postgres, and a mock
wouldn't actually verify that claim. DuckDB is also just the pipeline's own
local backend, not a stand-in invented for testing.
"""

import pandas as pd
import pytest
from sqlalchemy import create_engine, text

from src.config.settings import settings
from src.load.warehouse_loader import (
    clear_table,
    load_all,
    load_table,
    validate_required_columns,
)


@pytest.fixture
def duckdb_engine(tmp_path):
    engine = create_engine(f"duckdb:///{tmp_path / 'loader_test.duckdb'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA cdm"))
        conn.execute(text(
            "CREATE TABLE cdm.person "
            "(person_id INTEGER, gender_concept_id INTEGER, year_of_birth INTEGER)"
        ))
    return engine


@pytest.fixture
def duckdb_settings(monkeypatch, tmp_path):
    """Point the module-level settings singleton at a scratch DuckDB file for
    the duration of one test, so load_all() (which builds its own engine from
    settings.database_url) runs against something real and disposable."""
    monkeypatch.setattr(settings, "warehouse_backend", "duckdb")
    monkeypatch.setattr(settings, "duckdb_path", tmp_path / "settings_test.duckdb")
    return settings


class TestValidateRequiredColumns:
    def test_passes_when_present_and_non_null(self):
        df = pd.DataFrame({"person_id": [1, 2], "gender_concept_id": [8507, 8532], "year_of_birth": [1980, 1990]})
        validate_required_columns(df, "person")  # should not raise

    def test_raises_on_missing_column(self):
        df = pd.DataFrame({"person_id": [1]})
        with pytest.raises(ValueError, match="missing required column"):
            validate_required_columns(df, "person")

    def test_raises_on_null_values(self):
        df = pd.DataFrame({
            "person_id": [1, None], "gender_concept_id": [8507, 8532], "year_of_birth": [1980, 1990],
        })
        with pytest.raises(ValueError, match="null values"):
            validate_required_columns(df, "person")

    def test_no_requirements_for_unlisted_table(self):
        validate_required_columns(pd.DataFrame({"anything": [1]}), "some_unlisted_table")  # should not raise


class TestLoadAndClearTable:
    def test_load_then_clear(self, duckdb_engine):
        df = pd.DataFrame({"person_id": [1, 2], "gender_concept_id": [8507, 8532], "year_of_birth": [1980, 1990]})
        count = load_table(df, "person", duckdb_engine, schema="cdm")
        assert count == 2

        with duckdb_engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM cdm.person")).scalar() == 2

        clear_table("person", duckdb_engine, schema="cdm")
        with duckdb_engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM cdm.person")).scalar() == 0

    def test_load_raises_on_missing_required_value(self, duckdb_engine):
        df = pd.DataFrame({"person_id": [1], "gender_concept_id": [None], "year_of_birth": [1980]})
        with pytest.raises(ValueError):
            load_table(df, "person", duckdb_engine, schema="cdm")


class TestLoadAll:
    def test_loads_in_dependency_order(self, duckdb_settings):
        engine = create_engine(settings.database_url)
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA cdm"))
            conn.execute(text(
                "CREATE TABLE cdm.person (person_id INTEGER, gender_concept_id INTEGER, year_of_birth INTEGER)"
            ))
            conn.execute(text(
                "CREATE TABLE cdm.visit_occurrence (visit_occurrence_id INTEGER, person_id INTEGER, "
                "visit_concept_id INTEGER, visit_start_date DATE)"
            ))

        tables = {
            "visit_occurrence": pd.DataFrame({
                "visit_occurrence_id": [1], "person_id": [1],
                "visit_concept_id": [9202], "visit_start_date": pd.to_datetime(["2021-01-01"]).date,
            }),
            "person": pd.DataFrame({"person_id": [1], "gender_concept_id": [8507], "year_of_birth": [1980]}),
        }

        results = load_all(tables, schema="cdm")
        assert results == {"person": 1, "visit_occurrence": 1}

    def test_reloading_clears_previous_rows(self, duckdb_settings):
        engine = create_engine(settings.database_url)
        with engine.begin() as conn:
            conn.execute(text("CREATE SCHEMA cdm"))
            conn.execute(text(
                "CREATE TABLE cdm.person (person_id INTEGER, gender_concept_id INTEGER, year_of_birth INTEGER)"
            ))

        first = pd.DataFrame({"person_id": [1, 2], "gender_concept_id": [8507, 8532], "year_of_birth": [1980, 1990]})
        load_all({"person": first}, schema="cdm")

        second = pd.DataFrame({"person_id": [1], "gender_concept_id": [8507], "year_of_birth": [1980]})
        results = load_all({"person": second}, schema="cdm")

        assert results == {"person": 1}
        with engine.connect() as conn:
            assert conn.execute(text("SELECT COUNT(*) FROM cdm.person")).scalar() == 1
