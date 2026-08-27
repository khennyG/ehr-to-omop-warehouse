"""Great Expectations suites for source-level validation of Synthea CSV exports.

This runs right after extract, before anything touches the OMOP schema. It's a
different kind of check than src/extract/synthea_loader.py's validate_schema,
which only confirms the expected columns exist — this confirms the values in
them look like what a Synthea export should actually contain: null rates
within tolerance, categorical columns using only their expected values, dates
that parse, row counts that aren't suspiciously small. dqd_checks.py runs the
equivalent idea one stage later, against the loaded OMOP warehouse; this is
the same principle applied where a bad input file is cheapest to catch —
before hundreds of rows of bad data propagate through vocabulary mapping and
surrogate key generation.

Each table gets its own ephemeral GE context and expectation suite rather than
one suite for everything, because "gender is one of M/F" and "quantity is a
non-negative number" don't belong in the same failure report — a stakeholder
skimming results wants to see them grouped by the table they came from.
"""

import contextlib
import io
from dataclasses import dataclass

import great_expectations as gx
import pandas as pd
from great_expectations.expectations.expectation import Expectation
from loguru import logger


@dataclass
class SourceCheckResult:
    table_name: str
    success: bool
    evaluated: int
    successful: int
    failed_expectations: list[str]

    def __str__(self) -> str:
        status = "PASS" if self.success else "FAIL"
        return f"[{status}] {self.table_name}: {self.successful}/{self.evaluated} expectations met"


# GE's pandas execution engine evaluates expectations by materializing metrics
# per column in Python, not by pushing the check down into a query engine — fine
# at the row counts a single patient's chart produces, not fine at the row counts
# a several-thousand-patient observations table produces (a full run there was
# still going after several minutes). Validating a fixed-size random sample
# instead of the whole table is the standard way GE-based pipelines handle this at
# any real scale; a large source table is checked here for whether it exhibits a
# schema/null/range problem, not audited row-for-row.
MAX_VALIDATION_ROWS = 20_000


def _validate(df: pd.DataFrame, table_name: str, expectations: list[Expectation]) -> SourceCheckResult:
    if len(df) > MAX_VALIDATION_ROWS:
        logger.debug(f"  {table_name}: sampling {MAX_VALIDATION_ROWS:,} of {len(df):,} rows for validation")
        df = df.sample(n=MAX_VALIDATION_ROWS, random_state=42)

    context = gx.get_context(mode="ephemeral")

    data_source = context.data_sources.add_pandas(name=f"{table_name}_source")
    asset = data_source.add_dataframe_asset(name=f"{table_name}_asset")
    batch_definition = asset.add_batch_definition_whole_dataframe(f"{table_name}_batch")
    batch = batch_definition.get_batch(batch_parameters={"dataframe": df})

    suite = context.suites.add(gx.ExpectationSuite(name=f"{table_name}_suite"))
    for expectation in expectations:
        suite.add_expectation(expectation)

    # GE writes a tqdm progress bar straight to stderr per metric batch, with no
    # documented way to disable it from this call site — harmless, but it
    # drowns out loguru's own stderr sink. Contained to just this call so it
    # doesn't swallow any other stderr output.
    with contextlib.redirect_stderr(io.StringIO()):
        result = batch.validate(suite)

    failed = [
        r.expectation_config.type for r in result.results
        if not r.success and r.expectation_config is not None
    ]
    return SourceCheckResult(
        table_name=table_name,
        success=result.success,
        evaluated=result.statistics["evaluated_expectations"],
        successful=result.statistics["successful_expectations"],
        failed_expectations=failed,
    )


def _expect_patients() -> list[Expectation]:
    e = gx.expectations
    return [
        e.ExpectTableRowCountToBeBetween(min_value=1),
        e.ExpectColumnValuesToNotBeNull(column="Id"),
        e.ExpectColumnValuesToBeUnique(column="Id"),
        e.ExpectColumnValuesToNotBeNull(column="BIRTHDATE"),
        e.ExpectColumnValuesToBeInSet(column="GENDER", value_set=["M", "F"], mostly=0.99),
        e.ExpectColumnValuesToMatchStrftimeFormat(column="BIRTHDATE", strftime_format="%Y-%m-%d"),
    ]


def _expect_encounters() -> list[Expectation]:
    e = gx.expectations
    return [
        e.ExpectTableRowCountToBeBetween(min_value=1),
        e.ExpectColumnValuesToNotBeNull(column="Id"),
        e.ExpectColumnValuesToNotBeNull(column="PATIENT"),
        e.ExpectColumnValuesToBeInSet(
            column="ENCOUNTERCLASS",
            value_set=["ambulatory", "outpatient", "inpatient", "emergency", "urgentcare", "wellness"],
            mostly=0.95,
        ),
    ]


def _expect_conditions() -> list[Expectation]:
    e = gx.expectations
    return [
        e.ExpectColumnValuesToNotBeNull(column="PATIENT"),
        e.ExpectColumnValuesToNotBeNull(column="CODE"),
        e.ExpectColumnValuesToNotBeNull(column="START"),
    ]


def _expect_medications() -> list[Expectation]:
    e = gx.expectations
    return [
        e.ExpectColumnValuesToNotBeNull(column="PATIENT"),
        e.ExpectColumnValuesToNotBeNull(column="CODE"),
        e.ExpectColumnValuesToBeBetween(column="DISPENSES", min_value=0, mostly=0.99),
    ]


def _expect_observations() -> list[Expectation]:
    e = gx.expectations
    return [
        e.ExpectColumnValuesToNotBeNull(column="PATIENT"),
        e.ExpectColumnValuesToNotBeNull(column="CODE"),
        e.ExpectColumnValuesToNotBeNull(column="VALUE"),
    ]


def _expect_procedures() -> list[Expectation]:
    e = gx.expectations
    return [
        e.ExpectColumnValuesToNotBeNull(column="PATIENT"),
        e.ExpectColumnValuesToNotBeNull(column="CODE"),
    ]


TABLE_EXPECTATIONS = {
    "patients": _expect_patients,
    "encounters": _expect_encounters,
    "conditions": _expect_conditions,
    "medications": _expect_medications,
    "observations": _expect_observations,
    "procedures": _expect_procedures,
}


def validate_source_tables(staging: dict[str, pd.DataFrame]) -> list[SourceCheckResult]:
    """Run the expectation suite for every staging table present in `staging`.

    Tables without a registered expectation function are skipped rather than
    failing the run — this validates the six Synthea domains the pipeline
    knows about, not an arbitrary CSV someone points extract at.
    """
    logger.info("Running source-level data quality checks (Great Expectations)")
    results = []
    for table_name, df in staging.items():
        build_expectations = TABLE_EXPECTATIONS.get(table_name)
        if build_expectations is None:
            continue
        result = _validate(df, table_name, build_expectations())
        results.append(result)
        logger.log("SUCCESS" if result.success else "ERROR", str(result))
        if not result.success:
            logger.warning(f"  failed: {result.failed_expectations}")

    passed = sum(1 for r in results if r.success)
    logger.info(f"Source validation complete: {passed}/{len(results)} tables passed")
    return results
