"""Load transformed OMOP DataFrames into the warehouse (Postgres or DuckDB).

This module handles the final stage: writing OMOP-conformant DataFrames into
the CDM schema built by sql/schema/. It enforces table-level constraints
(not-null checks on required fields) before insertion and logs row counts for
pipeline monitoring.

Loading is idempotent: every table is cleared before any table is reloaded, in
the reverse of its dependency order, so a table with a foreign key never gets
deleted out from under a row that still references it. The tables themselves
are never dropped or recreated — they were built by sql/schema/ with real
primary and foreign key constraints, and this module's job is to respect those,
not regenerate a looser schema from whatever pandas infers off a DataFrame.
"""

from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text

from src.config.settings import settings
from src.db_utils import bulk_write

# On Postgres, sql/schema/ never has to be applied by this module — docker-compose
# mounts it into /docker-entrypoint-initdb.d and the container runs all four files at
# first boot. DuckDB has no equivalent bootstrap hook, so the local/demo backend
# applies the same files itself, in the same numbered order, the first time it sees
# an empty database. 03_constraints.sql is the one exception: DuckDB doesn't support
# adding a foreign key via ALTER TABLE (verified directly against 1.5.5 — every
# `alter table ... add constraint ... foreign key` in that file fails with "No
# support for that ALTER TABLE option yet!", while every statement in the other
# three files succeeds unchanged). The demo backend runs without enforced foreign
# keys as a result; Postgres is what actually holds the schema to its real
# constraints.
SCHEMA_DIR = Path(__file__).resolve().parents[2] / "sql" / "schema"
DUCKDB_SCHEMA_FILES = ["01_ddl.sql", "02_primary_keys.sql", "04_indices.sql"]


def _strip_sql_comments(sql: str) -> str:
    """Drop everything from `--` to end of line, on every line.

    A naive split on ';' breaks the moment a multi-line comment block sits
    between two statements — the comment's prose gets treated as part of
    whichever statement follows it. Stripping comments first, uniformly,
    means the split that comes after never has to guess.
    """
    return "\n".join(line[:idx] if (idx := line.find("--")) != -1 else line for line in sql.splitlines())


def _split_statements(sql: str) -> list[str]:
    return [s.strip() for s in _strip_sql_comments(sql).split(";") if s.strip()]


def init_duckdb_schema(schema: str = "cdm", schema_dir: Path = SCHEMA_DIR) -> None:
    """Apply the OMOP DDL to a local DuckDB file, if it hasn't been applied yet.

    No-ops against a Postgres backend — that schema comes from docker-compose's
    init hook, not from this function.
    """
    if settings.warehouse_backend != "duckdb":
        return

    engine = create_engine(settings.database_url)
    with engine.connect() as conn:
        already_initialized = conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            f"WHERE table_schema = '{schema}' AND table_name = 'person'"
        )).scalar()
    if already_initialized:
        logger.debug(f"DuckDB schema already initialized in {settings.duckdb_path}")
        return

    logger.info(f"Initializing DuckDB schema at {settings.duckdb_path}")
    for filename in DUCKDB_SCHEMA_FILES:
        statements = _split_statements((schema_dir / filename).read_text())
        with engine.begin() as conn:
            for stmt in statements:
                conn.execute(text(stmt))
        logger.info(f"  Applied {filename} ({len(statements)} statements)")


# Required non-null columns per OMOP table (subset — the full CDM has more)
REQUIRED_COLUMNS = {
    "person": ["person_id", "gender_concept_id", "year_of_birth"],
    "visit_occurrence": ["visit_occurrence_id", "person_id", "visit_concept_id", "visit_start_date"],
    "condition_occurrence": ["condition_occurrence_id", "person_id", "condition_concept_id", "condition_start_date"],
    "drug_exposure": ["drug_exposure_id", "person_id", "drug_concept_id", "drug_exposure_start_date"],
    "measurement": ["measurement_id", "person_id", "measurement_concept_id", "measurement_date"],
    "observation_period": ["observation_period_id", "person_id", "observation_period_start_date", "observation_period_end_date"],
}


def validate_required_columns(df: pd.DataFrame, table_name: str) -> None:
    """Check that required columns are present and non-null."""
    required = REQUIRED_COLUMNS.get(table_name, [])
    for col in required:
        if col not in df.columns:
            raise ValueError(f"[{table_name}] missing required column: {col}")
        null_count = df[col].isna().sum()
        if null_count > 0:
            raise ValueError(
                f"[{table_name}] column {col} has {null_count:,} null values"
            )


# Dependency order clinical tables must load in — person before anything that
# references person_id, visit_occurrence before anything that references
# visit_occurrence_id. Clearing runs in reverse so a delete never orphans a row
# that another table's foreign key still points at.
LOAD_ORDER = [
    "person", "observation_period", "visit_occurrence",
    "condition_occurrence", "drug_exposure", "procedure_occurrence",
    "measurement", "observation", "death",
]


def clear_table(table_name: str, engine, schema: str) -> None:
    """Delete all rows from a table without touching its structure or constraints."""
    with engine.begin() as conn:
        conn.execute(text(f"DELETE FROM {schema}.{table_name}"))


def load_table(
    df: pd.DataFrame,
    table_name: str,
    engine,
    schema: str = "cdm",
) -> int:
    """Bulk-insert a DataFrame into an existing OMOP table. Returns the row count.

    Assumes the table has already been cleared by the caller — load_all clears
    every table up front, in reverse dependency order, before any table is
    reloaded, so foreign keys are never violated mid-run.
    """
    validate_required_columns(df, table_name)

    logger.info(f"Loading {len(df):,} rows into {schema}.{table_name}")

    bulk_write(df, table_name, engine, schema=schema, if_exists="append")

    logger.info(f"  Loaded {len(df):,} rows into {schema}.{table_name}")
    return len(df)


def load_all(tables: dict[str, pd.DataFrame], schema: str = "cdm") -> dict[str, int]:
    """Load all transformed OMOP tables into the warehouse.

    Args:
        tables: dict mapping OMOP table names to DataFrames
        schema: target schema name

    Returns:
        dict mapping table names to row counts
    """
    engine = create_engine(settings.database_url)

    ordered_names = [name for name in LOAD_ORDER if name in tables]
    remaining_names = [name for name in tables if name not in ordered_names]
    all_names = ordered_names + remaining_names

    logger.info(f"Clearing {len(all_names)} OMOP tables before reload")
    for table_name in reversed(all_names):
        clear_table(table_name, engine, schema)

    results = {}
    for table_name in all_names:
        results[table_name] = load_table(tables[table_name], table_name, engine, schema)

    total = sum(results.values())
    logger.info(f"Load complete: {total:,} rows across {len(results)} OMOP tables")
    return results


# Vocabulary tables have their own dependency order, and it isn't the clinical one:
# domain/vocabulary/concept_class have no dependencies, concept depends on all three,
# relationship has no dependencies, and everything else depends on concept and/or
# relationship. VocabularyMapper reads the same Athena-format files into memory for
# code-resolution lookups during transform — this is what makes the resulting
# concept_ids valid rows in the actual warehouse, which is what the foreign keys in
# sql/schema/03_constraints.sql and DQD's check_concept_valid both need.
VOCAB_LOAD_ORDER = [
    "domain", "vocabulary", "concept_class", "concept", "relationship",
    "concept_relationship", "concept_synonym", "concept_ancestor", "drug_strength",
]

VOCAB_FILES = {
    "domain": "DOMAIN.csv",
    "vocabulary": "VOCABULARY.csv",
    "concept_class": "CONCEPT_CLASS.csv",
    "concept": "CONCEPT.csv",
    "relationship": "RELATIONSHIP.csv",
    "concept_relationship": "CONCEPT_RELATIONSHIP.csv",
    "concept_synonym": "CONCEPT_SYNONYM.csv",
    "concept_ancestor": "CONCEPT_ANCESTOR.csv",
    "drug_strength": "DRUG_STRENGTH.csv",
}

# Columns that arrive as Athena-format date strings and need to become actual
# date objects before to_sql hands them to a `date`-typed column.
VOCAB_DATE_COLUMNS = {
    "concept": ["valid_start_date", "valid_end_date"],
    "concept_relationship": ["valid_start_date", "valid_end_date"],
    "drug_strength": ["valid_start_date", "valid_end_date"],
}


def load_vocabulary(vocab_dir: Path, schema: str = "cdm") -> dict[str, int]:
    """Load Athena-format vocabulary files into the warehouse's vocabulary tables.

    Whatever's present in vocab_dir loads — the demo seed from
    scripts/build_demo_vocabulary.py covers concept, concept_relationship,
    vocabulary, domain, and concept_class; a real Athena download adds
    concept_synonym, concept_ancestor, and drug_strength on top. Tables whose
    file isn't present are skipped rather than failing the run, since a
    download from Athena is under no obligation to be complete for a given release.
    """
    engine = create_engine(settings.database_url)
    present = [name for name in VOCAB_LOAD_ORDER if (vocab_dir / VOCAB_FILES[name]).exists()]

    logger.info(f"Clearing {len(present)} vocabulary tables before reload")
    for table_name in reversed(present):
        clear_table(table_name, engine, schema)

    results = {}
    for table_name in present:
        path = vocab_dir / VOCAB_FILES[table_name]
        # "None" is a real OMOP vocabulary_id — the vocabulary concept_id=0
        # belongs to — not a placeholder for a missing value. pandas' default
        # NA sentinel list treats the literal text "None" (along with "NULL",
        # "N/A", etc.) as null on read, which would silently turn that row's
        # vocabulary_id into NaN. Only a genuinely empty field should parse
        # as null here.
        df = pd.read_csv(path, sep="\t", low_memory=False, keep_default_na=False, na_values=[""])
        df.columns = [c.lower() for c in df.columns]
        for date_col in VOCAB_DATE_COLUMNS.get(table_name, []):
            df[date_col] = pd.to_datetime(df[date_col]).dt.date
        results[table_name] = load_table(df, table_name, engine, schema)

    total = sum(results.values())
    logger.info(f"Vocabulary load complete: {total:,} rows across {len(results)} tables")
    return results
