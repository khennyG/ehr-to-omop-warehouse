"""Extract module: load raw Synthea CSV exports into staging tables.

Synthea outputs one CSV per clinical domain (patients, encounters, conditions,
medications, observations, procedures, etc.). This module reads each file,
validates its schema against expected columns, and bulk-inserts rows into
staging tables in the warehouse (Postgres or DuckDB — see
src/config/settings.py).

The staging tables mirror the CSV structure exactly — no transformation
happens here. That separation keeps extract idempotent: re-running it
replaces staging data without affecting downstream OMOP tables.
"""

from pathlib import Path

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine

from src.config.settings import settings
from src.db_utils import bulk_write

# Synthea CSV files and their expected column sets. If a file is missing
# columns, the extract stage fails loudly rather than producing silent NULLs.
SYNTHEA_TABLES = {
    "patients": [
        "Id", "BIRTHDATE", "DEATHDATE", "SSN", "DRIVERS", "PASSPORT",
        "PREFIX", "FIRST", "LAST", "SUFFIX", "MAIDEN", "MARITAL",
        "RACE", "ETHNICITY", "GENDER", "BIRTHPLACE", "ADDRESS", "CITY",
        "STATE", "COUNTY", "FIPS", "ZIP", "LAT", "LON",
        "HEALTHCARE_EXPENSES", "HEALTHCARE_COVERAGE", "INCOME",
    ],
    "encounters": [
        "Id", "START", "STOP", "PATIENT", "ORGANIZATION", "PROVIDER",
        "PAYER", "ENCOUNTERCLASS", "CODE", "DESCRIPTION",
        "BASE_ENCOUNTER_COST", "TOTAL_CLAIM_COST", "PAYER_COVERAGE",
        "REASONCODE", "REASONDESCRIPTION",
    ],
    "conditions": [
        "START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION",
    ],
    "medications": [
        "START", "STOP", "PATIENT", "PAYER", "ENCOUNTER", "CODE",
        "DESCRIPTION", "BASE_COST", "PAYER_COVERAGE", "DISPENSES",
        "TOTALCOST", "REASONCODE", "REASONDESCRIPTION",
    ],
    "observations": [
        "DATE", "PATIENT", "ENCOUNTER", "CATEGORY", "CODE",
        "DESCRIPTION", "VALUE", "UNITS", "TYPE",
    ],
    "procedures": [
        "START", "STOP", "PATIENT", "ENCOUNTER", "CODE", "DESCRIPTION",
        "BASE_COST", "REASONCODE", "REASONDESCRIPTION",
    ],
}


def validate_schema(df: pd.DataFrame, table_name: str) -> None:
    """Check that a DataFrame has at least the expected columns."""
    expected = set(SYNTHEA_TABLES[table_name])
    actual = set(df.columns)
    missing = expected - actual
    if missing:
        raise ValueError(
            f"[{table_name}] missing columns: {sorted(missing)}"
        )


def load_csv(csv_path: Path, table_name: str) -> pd.DataFrame:
    """Read a single Synthea CSV and validate its schema."""
    logger.info(f"Reading {csv_path.name} ({csv_path.stat().st_size / 1e6:.1f} MB)")
    df = pd.read_csv(csv_path, low_memory=False)
    validate_schema(df, table_name)
    logger.info(f"  {len(df):,} rows, {len(df.columns)} columns")
    return df


def load_to_staging(df: pd.DataFrame, table_name: str, engine) -> int:
    """Bulk-insert a DataFrame into a staging table, replacing existing data."""
    staging_table = f"stg_{table_name}"
    bulk_write(df, staging_table, engine, if_exists="replace")
    logger.info(f"  Loaded {len(df):,} rows into {staging_table}")
    return len(df)


def run_extract() -> dict[str, int]:
    """Run the full extract stage: read all Synthea CSVs into staging tables.

    Returns a dict mapping table names to row counts.
    """
    synthea_dir = settings.synthea_output_dir
    if not synthea_dir.exists():
        raise FileNotFoundError(
            f"Synthea output directory not found: {synthea_dir}. "
            f"Run `make synthea` first."
        )

    engine = create_engine(settings.database_url)
    results = {}

    for table_name in SYNTHEA_TABLES:
        csv_path = synthea_dir / f"{table_name}.csv"
        if not csv_path.exists():
            logger.warning(f"Skipping {table_name}: {csv_path} not found")
            continue
        df = load_csv(csv_path, table_name)
        row_count = load_to_staging(df, table_name, engine)
        results[table_name] = row_count

    logger.info(f"Extract complete: {sum(results.values()):,} total rows across {len(results)} tables")
    return results


if __name__ == "__main__":
    run_extract()
