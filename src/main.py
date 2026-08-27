"""Pipeline entrypoint: orchestrate the full ETL from Synthea to OMOP CDM.

Usage:
    python -m src.main                # Run full pipeline
    python -m src.main --stage extract  # Run single stage
"""

import sys
import time

import click
import pandas as pd
from loguru import logger
from sqlalchemy import create_engine

from src.config.settings import settings

# Synthea staging tables read at transform time, and the OMOP source column each
# one's surrogate keys get looked up by when later tables need to reference them.
STAGING_TABLES = [
    "patients", "encounters", "conditions", "medications", "observations", "procedures",
]


def read_staging_tables(engine) -> dict[str, pd.DataFrame]:
    """Read every stg_* table back out of the warehouse for the transform stage.

    Reading from staging rather than re-parsing the raw CSVs is what makes
    extract and transform independently re-runnable stages instead of one
    fused step — either can run on its own against whatever the other last
    left in the database.
    """
    staging = {}
    for name in STAGING_TABLES:
        staging[name] = pd.read_sql(f"select * from stg_{name}", engine)
        logger.info(f"  Read {len(staging[name]):,} rows from stg_{name}")
    return staging


def write_processed_tables(tables: dict[str, pd.DataFrame]) -> None:
    """Persist transformed OMOP tables to parquet so the load stage can run on
    its own, without the transform stage having run in the same process."""
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        path = settings.processed_dir / f"{name}.parquet"
        df.to_parquet(path, index=False)
        logger.info(f"  Wrote {len(df):,} rows to {path}")


def read_processed_tables() -> dict[str, pd.DataFrame]:
    """Read the parquet files the transform stage produced, for the load stage."""
    tables = {}
    for path in sorted(settings.processed_dir.glob("*.parquet")):
        tables[path.stem] = pd.read_parquet(path)
    if not tables:
        raise FileNotFoundError(
            f"No transformed tables found in {settings.processed_dir}. "
            f"Run `python -m src.main --stage transform` first."
        )
    return tables


def configure_logging():
    """Set up structured logging with loguru."""
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> - <level>{message}</level>"
        ),
    )
    logger.add(
        "logs/pipeline_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
    )


@click.command()
@click.option(
    "--stage",
    type=click.Choice(["extract", "transform", "load", "quality", "all"]),
    default="all",
    help="Pipeline stage to run",
)
@click.option("--population", type=int, default=None, help="Override Synthea population size")
def main(stage: str, population: int | None):
    """Run the EHR-to-OMOP ETL pipeline."""
    configure_logging()

    if population:
        settings.synthea_population = population

    logger.info("=" * 60)
    logger.info("EHR-to-OMOP Pipeline")
    logger.info(f"  Database: {settings.postgres_host}:{settings.postgres_port}/{settings.postgres_db}")
    logger.info(f"  Synthea dir: {settings.synthea_output_dir}")
    logger.info(f"  Stage: {stage}")
    logger.info("=" * 60)

    start = time.time()

    if stage in ("extract", "all"):
        logger.info("── STAGE: EXTRACT ──")
        from src.extract.synthea_loader import run_extract
        from src.quality.ge_suites import validate_source_tables

        run_extract()

        engine = create_engine(settings.database_url)
        staging = read_staging_tables(engine)
        source_results = validate_source_tables(staging)
        if any(not r.success for r in source_results):
            logger.warning("One or more source tables failed validation — see above")
        logger.info(f"Extract complete in {time.time() - start:.1f}s")

    if stage in ("transform", "all"):
        logger.info("── STAGE: TRANSFORM ──")
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

        mapper = VocabularyMapper()
        mapper.load()

        engine = create_engine(settings.database_url)
        staging = read_staging_tables(engine)

        person = transform_person(staging["patients"], mapper)
        person_lookup = dict(zip(person["person_source_value"], person["person_id"]))

        visits = transform_visit_occurrence(staging["encounters"], person_lookup, mapper)
        visit_lookup = dict(zip(visits["encounter_source_value"], visits["visit_occurrence_id"]))
        # encounter_source_value only exists to build that lookup — it isn't
        # a real OMOP visit_occurrence column, so it doesn't get loaded as
        # one. (Every other transform_* function keys off the *source*
        # table's own natural key instead of a column it invents, so this
        # cleanup is specific to visits.)
        visits = visits.drop(columns=["encounter_source_value"])

        tables = {
            "person": person,
            "visit_occurrence": visits,
            "observation_period": transform_observation_period(visits),
            "condition_occurrence": transform_condition_occurrence(
                staging["conditions"], person_lookup, visit_lookup, mapper
            ),
            "drug_exposure": transform_drug_exposure(
                staging["medications"], person_lookup, visit_lookup, mapper
            ),
            "procedure_occurrence": transform_procedure_occurrence(
                staging["procedures"], person_lookup, visit_lookup, mapper
            ),
            "measurement": transform_measurement(
                staging["observations"], person_lookup, visit_lookup, mapper
            ),
            "observation": transform_observation(
                staging["observations"], person_lookup, visit_lookup, mapper
            ),
            "death": transform_death(staging["patients"], person_lookup),
        }

        write_processed_tables(tables)
        logger.info(f"Transform complete in {time.time() - start:.1f}s")

    if stage in ("load", "all"):
        logger.info("── STAGE: LOAD ──")
        from src.load.warehouse_loader import (
            init_duckdb_schema,
            load_all,
            load_vocabulary,
        )

        init_duckdb_schema()
        load_vocabulary(settings.vocabulary_dir)
        tables = read_processed_tables()
        load_all(tables)
        logger.info(f"Load complete in {time.time() - start:.1f}s")

    if stage in ("quality", "all"):
        logger.info("── STAGE: QUALITY ──")
        from src.quality.dqd_checks import DQDChecker, Severity
        checker = DQDChecker()
        results = checker.run_all()
        summary = checker.summary_dataframe()
        logger.info(f"Quality checks: {summary['passed'].sum()}/{len(summary)} passed")

        # The gate the architecture diagram calls for: a critical DQD
        # failure has to actually stop the pipeline, not just get logged and
        # ignored. This is what the Airflow DAG's quality task depends on to
        # block dbt_build when the warehouse itself failed its own checks.
        critical_failures = [
            r for r in results if not r.passed and r.severity == Severity.CRITICAL
        ]
        if critical_failures:
            logger.error(f"{len(critical_failures)} critical quality check(s) failed — halting pipeline")
            sys.exit(1)

    elapsed = time.time() - start
    logger.info(f"Pipeline finished in {elapsed:.1f}s")


if __name__ == "__main__":
    main()
