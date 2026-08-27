"""End-to-end integration test: extract -> transform -> load -> quality
through the real CLI entrypoint, not the individual functions in isolation.

Everything else in tests/ verifies one module's behavior against a
hand-built fixture. This is the one test that runs `python -m src.main`
itself (via Click's CliRunner, in-process rather than a subprocess, so a
failure's traceback points at the actual line rather than opaque subprocess
output) against a small generated population and a real vocabulary seed,
the same two inputs a developer running this pipeline locally would produce
with scripts/generate_demo_data.py and scripts/build_demo_vocabulary.py.
"""


import numpy as np
import pandas as pd
import pytest
from click.testing import CliRunner
from sqlalchemy import create_engine, text

from scripts.build_demo_vocabulary import TABLE_BUILDERS
from scripts.generate_demo_data import _generate_patient_events, generate_patients


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    """Point settings at isolated temp directories, generate a small demo
    population and vocabulary into them, and hand back the paths."""
    from src.config.settings import settings

    synthea_dir = tmp_path / "synthea"
    vocab_dir = tmp_path / "vocab"
    processed_dir = tmp_path / "processed"
    duckdb_path = tmp_path / "integration.duckdb"

    monkeypatch.setattr(settings, "warehouse_backend", "duckdb")
    monkeypatch.setattr(settings, "duckdb_path", duckdb_path)
    monkeypatch.setattr(settings, "synthea_output_dir", synthea_dir)
    monkeypatch.setattr(settings, "vocabulary_dir", vocab_dir)
    monkeypatch.setattr(settings, "processed_dir", processed_dir)
    monkeypatch.setattr(settings, "log_level", "WARNING")

    # Demo vocabulary
    vocab_dir.mkdir(parents=True)
    for filename, builder in TABLE_BUILDERS.items():
        builder().to_csv(vocab_dir / filename, sep="\t", index=False)

    # A small synthetic population — same generator the real demo path uses,
    # just few enough patients to keep this test fast.
    synthea_dir.mkdir(parents=True)
    rng = np.random.default_rng(7)
    patients = generate_patients(60, rng)
    encounters, conditions, medications, observations, procedures = [], [], [], [], []
    for _, row in patients.iterrows():
        tl = _generate_patient_events(row, rng)
        encounters.extend(tl.encounters)
        conditions.extend(tl.conditions)
        medications.extend(tl.medications)
        observations.extend(tl.observations)
        procedures.extend(tl.procedures)

    tables = {
        "patients": patients.drop(columns=["_age_years"]),
        "encounters": pd.DataFrame(encounters),
        "conditions": pd.DataFrame(conditions),
        "medications": pd.DataFrame(medications),
        "observations": pd.DataFrame(observations),
        "procedures": pd.DataFrame(procedures),
    }
    for name, df in tables.items():
        df.to_csv(synthea_dir / f"{name}.csv", index=False)

    return {"duckdb_path": duckdb_path}


def test_full_pipeline_runs_end_to_end(pipeline_env):
    from src.main import main

    runner = CliRunner()
    result = runner.invoke(main, ["--stage", "all"])

    assert result.exit_code == 0, result.output or str(result.exception)

    engine = create_engine(f"duckdb:///{pipeline_env['duckdb_path']}")
    with engine.connect() as conn:
        person_count = conn.execute(text("SELECT COUNT(*) FROM cdm.person")).scalar()
        visit_count = conn.execute(text("SELECT COUNT(*) FROM cdm.visit_occurrence")).scalar()

        # Referential integrity: every visit's person_id has to resolve to
        # a real person, the same thing sql/schema/03_constraints.sql
        # enforces for real on Postgres (DuckDB doesn't support that
        # constraint — see warehouse_loader.py's DUCKDB_SCHEMA_FILES note —
        # so this test is what actually checks it on this backend).
        orphaned_visits = conn.execute(text(
            "SELECT COUNT(*) FROM cdm.visit_occurrence v "
            "LEFT JOIN cdm.person p ON p.person_id = v.person_id "
            "WHERE p.person_id IS NULL"
        )).scalar()

    assert person_count == 60
    assert visit_count > 0
    assert orphaned_visits == 0


def test_pipeline_fails_loudly_on_missing_source_data(tmp_path, monkeypatch):
    """extract should refuse to run quietly against an empty source directory."""
    from src.config.settings import settings
    from src.main import main

    monkeypatch.setattr(settings, "warehouse_backend", "duckdb")
    monkeypatch.setattr(settings, "duckdb_path", tmp_path / "empty.duckdb")
    monkeypatch.setattr(settings, "synthea_output_dir", tmp_path / "nonexistent")
    monkeypatch.setattr(settings, "log_level", "WARNING")

    runner = CliRunner()
    result = runner.invoke(main, ["--stage", "extract"])

    assert result.exit_code != 0
