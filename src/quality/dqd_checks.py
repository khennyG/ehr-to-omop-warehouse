"""Data Quality Dashboard (DQD) checks for the OMOP CDM warehouse.

Implements a subset of the OHDSI Data Quality Dashboard framework. The
original DQD defines ~3,500 checks across five categories. This module
implements the most critical checks that cover the majority of real-world
data quality issues:

  1. Completeness — are required fields populated?
  2. Conformance — do values fall within expected domains?
  3. Plausibility — are values clinically reasonable?
  4. Temporal consistency — do date sequences make sense?

Each check returns a CheckResult with pass/fail status, the metric value,
and a human-readable description. The pipeline halts on critical failures
and logs warnings for non-critical issues.
"""

from dataclasses import dataclass
from enum import Enum

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text

from src.config.settings import settings


class Severity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class CheckResult:
    check_name: str
    table_name: str
    category: str
    passed: bool
    metric_value: float
    threshold: float
    severity: Severity
    description: str

    def __str__(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        return (
            f"[{status}] {self.check_name} on {self.table_name}: "
            f"{self.metric_value:.2f} (threshold: {self.threshold:.2f}) "
            f"[{self.severity.value}]"
        )


class DQDChecker:
    """Run OHDSI-style data quality checks against the OMOP CDM warehouse."""

    def __init__(self, database_url: str | None = None, schema: str = "cdm"):
        self.engine = create_engine(database_url or settings.database_url)
        self.schema = schema
        self.results: list[CheckResult] = []

    def _query(self, sql: str) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn)

    # ── Completeness checks ──

    def check_completeness(self, table: str, column: str, threshold: float = 0.95) -> CheckResult:
        """Check that a column is populated above a minimum threshold."""
        df = self._query(
            f"SELECT COUNT(*) as total, "
            f"COUNT({column}) as non_null "
            f"FROM {self.schema}.{table}"
        )
        total = df["total"].iloc[0]
        non_null = df["non_null"].iloc[0]
        rate = non_null / total if total > 0 else 0.0

        result = CheckResult(
            check_name=f"completeness_{column}",
            table_name=table,
            category="completeness",
            passed=rate >= threshold,
            metric_value=rate,
            threshold=threshold,
            severity=Severity.CRITICAL if threshold >= 0.99 else Severity.WARNING,
            description=f"{column} is {rate:.1%} populated ({non_null:,}/{total:,})",
        )
        self.results.append(result)
        return result

    # ── Conformance checks ──

    def check_concept_valid(self, table: str, concept_column: str) -> CheckResult:
        """Check that concept_id values reference valid entries in the concept table."""
        df = self._query(
            f"SELECT COUNT(*) as total, "
            f"COUNT(CASE WHEN c.concept_id IS NOT NULL THEN 1 END) as valid "
            f"FROM {self.schema}.{table} t "
            f"LEFT JOIN {self.schema}.concept c ON t.{concept_column} = c.concept_id "
            f"WHERE t.{concept_column} != 0"
        )
        total = df["total"].iloc[0]
        valid = df["valid"].iloc[0]
        rate = valid / total if total > 0 else 1.0

        result = CheckResult(
            check_name=f"concept_valid_{concept_column}",
            table_name=table,
            category="conformance",
            passed=rate >= 0.95,
            metric_value=rate,
            threshold=0.95,
            severity=Severity.CRITICAL,
            description=f"{rate:.1%} of {concept_column} values reference valid concepts",
        )
        self.results.append(result)
        return result

    # ── Plausibility checks ──

    def check_value_range(
        self, table: str, column: str,
        min_val: float, max_val: float,
        threshold: float = 0.99,
    ) -> CheckResult:
        """Check that numeric values fall within a clinically plausible range."""
        df = self._query(
            f"SELECT COUNT(*) as total, "
            f"COUNT(CASE WHEN {column} BETWEEN {min_val} AND {max_val} THEN 1 END) as in_range "
            f"FROM {self.schema}.{table} "
            f"WHERE {column} IS NOT NULL"
        )
        total = df["total"].iloc[0]
        in_range = df["in_range"].iloc[0]
        rate = in_range / total if total > 0 else 1.0

        result = CheckResult(
            check_name=f"plausible_range_{column}",
            table_name=table,
            category="plausibility",
            passed=rate >= threshold,
            metric_value=rate,
            threshold=threshold,
            severity=Severity.WARNING,
            description=f"{rate:.1%} of {column} values are within [{min_val}, {max_val}]",
        )
        self.results.append(result)
        return result

    # ── Temporal consistency checks ──

    def check_temporal_order(
        self, table: str,
        start_col: str, end_col: str,
        threshold: float = 0.99,
    ) -> CheckResult:
        """Check that start dates come before end dates."""
        df = self._query(
            f"SELECT COUNT(*) as total, "
            f"COUNT(CASE WHEN {start_col} <= {end_col} THEN 1 END) as ordered "
            f"FROM {self.schema}.{table} "
            f"WHERE {start_col} IS NOT NULL AND {end_col} IS NOT NULL"
        )
        total = df["total"].iloc[0]
        ordered = df["ordered"].iloc[0]
        rate = ordered / total if total > 0 else 1.0

        result = CheckResult(
            check_name=f"temporal_order_{start_col}_before_{end_col}",
            table_name=table,
            category="temporal",
            passed=rate >= threshold,
            metric_value=rate,
            threshold=threshold,
            severity=Severity.CRITICAL,
            description=f"{rate:.1%} of records have {start_col} <= {end_col}",
        )
        self.results.append(result)
        return result

    # ── Run all checks ──

    def run_all(self) -> list[CheckResult]:
        """Run the standard DQD check suite and return results."""
        logger.info("Running OMOP DQD quality checks")

        # Completeness
        for table, columns in [
            ("person", ["person_id", "gender_concept_id", "year_of_birth"]),
            ("visit_occurrence", ["visit_occurrence_id", "person_id", "visit_start_date"]),
            ("condition_occurrence", ["condition_occurrence_id", "person_id", "condition_concept_id"]),
            ("drug_exposure", ["drug_exposure_id", "person_id", "drug_concept_id"]),
        ]:
            for col in columns:
                self.check_completeness(table, col, threshold=0.99)

        # condition_end_date isn't a required OMOP field, and shouldn't read
        # as one — most conditions in a real population are chronic or
        # still active, so a low threshold here checks that *some*
        # meaningful fraction resolved, not that nearly all of them did.
        self.check_completeness("condition_occurrence", "condition_end_date", threshold=0.30)

        # Conformance
        self.check_concept_valid("person", "gender_concept_id")
        self.check_concept_valid("condition_occurrence", "condition_concept_id")
        self.check_concept_valid("drug_exposure", "drug_concept_id")

        # Plausibility
        self.check_value_range("person", "year_of_birth", 1900, 2026)

        # Temporal
        self.check_temporal_order("visit_occurrence", "visit_start_date", "visit_end_date")
        self.check_temporal_order("drug_exposure", "drug_exposure_start_date", "drug_exposure_end_date")
        self.check_temporal_order("condition_occurrence", "condition_start_date", "condition_end_date")

        # Summary
        passed = sum(1 for r in self.results if r.passed)
        failed = sum(1 for r in self.results if not r.passed)
        critical_failures = [r for r in self.results if not r.passed and r.severity == Severity.CRITICAL]

        logger.info(f"DQD complete: {passed} passed, {failed} failed")
        for r in self.results:
            logger.log("SUCCESS" if r.passed else "ERROR", str(r))

        if critical_failures:
            logger.error(f"{len(critical_failures)} CRITICAL failures — pipeline should halt")

        return self.results

    def summary_dataframe(self) -> pd.DataFrame:
        """Return results as a DataFrame for visualization."""
        return pd.DataFrame([
            {
                "check": r.check_name,
                "table": r.table_name,
                "category": r.category,
                "passed": r.passed,
                "metric": r.metric_value,
                "threshold": r.threshold,
                "severity": r.severity.value,
                "description": r.description,
            }
            for r in self.results
        ])
