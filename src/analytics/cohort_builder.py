"""Cohort builder: define and execute temporal phenotype definitions.

A cohort in OMOP is a set of persons who satisfy a combination of inclusion
criteria over a time window. This module provides a programmatic interface
for defining cohorts — the same logic that OHDSI's ATLAS tool exposes
through a GUI, but expressed as composable Python objects that are version-
controlled and reproducible.

Three shapes of phenotype show up often enough in practice to warrant their
own execution path, and this module has one for each:

  execute()                       an index event, optionally followed by an
                                   outcome event within N days — works across
                                   any pair of clinical domains, not just
                                   drug-then-condition, since "diagnosis
                                   followed by complication" (condition ->
                                   condition) is exactly as common a phenotype
                                   shape as "prescription followed by adverse
                                   event" (drug -> condition).
  execute_escalation()             a sequence of drug exposures moving up a
                                   defined potency ladder within a window —
                                   opioid dose escalation is the canonical
                                   example, but the shape generalizes to any
                                   ordered progression.
  execute_concurrent_drug_count()  N or more distinct drugs with overlapping
                                   active date ranges at some point in time —
                                   polypharmacy has no "first this, then
                                   that" temporal story at all, just a count
                                   of what's active simultaneously.

src/analytics/predefined_cohorts.py wires concrete parameters onto these
three shapes for the phenotypes this project actually reports on.

Typical usage:
    builder = CohortBuilder()
    defn = builder.define(
        name="diabetes_mi",
        index_domain="Condition", index_terms=["diabetes"],
        outcome_domain="Condition", outcome_terms=["myocardial infarction"],
        temporal_window_days=365,
    )
    result = builder.execute(defn)
    attrition = builder.attrition_dataframe(result)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
from loguru import logger
from sqlalchemy import create_engine, text

from src.config.settings import settings

# Which OMOP table, concept_id column, and start-date column a domain resolves
# to. Every domain-agnostic method in this module is really just this lookup
# plus one shared SQL shape.
DOMAIN_TABLES = {
    "Drug": ("drug_exposure", "drug_concept_id", "drug_exposure_start_date"),
    "Condition": ("condition_occurrence", "condition_concept_id", "condition_start_date"),
}


@dataclass
class CohortDefinition:
    """A structured cohort definition: an index event, optionally followed by
    an outcome event in a different (or the same) domain, within a window."""
    name: str
    description: str
    index_domain: str = "Condition"
    index_concept_ids: list[int] = field(default_factory=list)
    index_terms: list[str] = field(default_factory=list)
    outcome_domain: str | None = None
    outcome_concept_ids: list[int] = field(default_factory=list)
    outcome_terms: list[str] = field(default_factory=list)
    temporal_window_days: int = 90
    require_index_first: bool = True
    min_age: int | None = None
    max_age: int | None = None


@dataclass
class CohortResult:
    """Results of executing a cohort definition."""
    definition: CohortDefinition
    members: pd.DataFrame
    attrition: list[dict]
    total_count: int


class CohortBuilder:
    """Build and execute OMOP cohort definitions."""

    def __init__(self, database_url: str | None = None, schema: str = "cdm"):
        self.engine = create_engine(database_url or settings.database_url)
        self.schema = schema

    def _query(self, sql: str, params: dict | None = None) -> pd.DataFrame:
        with self.engine.connect() as conn:
            return pd.read_sql(text(sql), conn, params=params)

    def _resolve_concepts(self, domain: str, terms: list[str]) -> list[int]:
        """Search concept_name for each term and union the matches.

        A phenotype's outcome is rarely one exact concept — "a cardiovascular
        event" is several conditions, not one — so this takes a list of
        search terms and returns the union of every match across all of
        them, rather than requiring the caller to pre-resolve concept IDs by
        hand.
        """
        ids: set[int] = set()
        for term in terms:
            matches = self._query(
                f"SELECT concept_id FROM {self.schema}.concept "
                f"WHERE LOWER(concept_name) LIKE :pattern "
                f"AND domain_id = :domain AND standard_concept = 'S'",
                params={"pattern": f"%{term.lower()}%", "domain": domain},
            )
            ids.update(matches["concept_id"].tolist())
        return sorted(ids)

    def define(
        self,
        name: str,
        index_domain: str,
        index_terms: list[str],
        outcome_domain: str | None = None,
        outcome_terms: list[str] | None = None,
        temporal_window_days: int = 90,
        require_index_first: bool = True,
        min_age: int | None = None,
        max_age: int | None = None,
    ) -> CohortDefinition:
        """Create a cohort definition from human-readable search terms.

        index_domain/outcome_domain are "Drug" or "Condition" — any
        combination works, since both resolve through the same concept
        table and the same drug_exposure/condition_occurrence lookup.
        """
        index_ids = self._resolve_concepts(index_domain, index_terms)
        logger.info(f"  Index [{index_domain}] {index_terms} resolved to {len(index_ids)} concept IDs")

        outcome_ids: list[int] = []
        if outcome_domain and outcome_terms:
            outcome_ids = self._resolve_concepts(outcome_domain, outcome_terms)
            logger.info(f"  Outcome [{outcome_domain}] {outcome_terms} resolved to {len(outcome_ids)} concept IDs")

        description = f"{index_domain} {index_terms}"
        if outcome_domain:
            description += f" -> {outcome_domain} {outcome_terms} within {temporal_window_days} days"

        return CohortDefinition(
            name=name,
            description=description,
            index_domain=index_domain,
            index_concept_ids=index_ids,
            index_terms=index_terms,
            outcome_domain=outcome_domain,
            outcome_concept_ids=outcome_ids,
            outcome_terms=outcome_terms or [],
            temporal_window_days=temporal_window_days,
            require_index_first=require_index_first,
            min_age=min_age,
            max_age=max_age,
        )

    def _first_event_dates(self, domain: str, concept_ids: list[int], person_ids: list[int] | None = None) -> pd.DataFrame:
        """First occurrence date per person for a set of concepts in a domain."""
        table, concept_col, date_col = DOMAIN_TABLES[domain]
        concept_list = ",".join(str(c) for c in concept_ids)
        person_filter = ""
        if person_ids is not None:
            person_list = ",".join(str(p) for p in person_ids[:10000])
            person_filter = f"AND person_id IN ({person_list})"
        return self._query(
            f"SELECT DISTINCT person_id, MIN({date_col}) as first_event_date "
            f"FROM {self.schema}.{table} "
            f"WHERE {concept_col} IN ({concept_list}) {person_filter} "
            f"GROUP BY person_id"
        )

    def execute(self, defn: CohortDefinition) -> CohortResult:
        """Execute a cohort definition and return matching patients.

        1. Find all patients with the index event
        2. Find all patients (among those) with the outcome event
        3. Apply the temporal constraint (index before outcome within N days)
        4. Apply demographic filters
        5. Track attrition at each step
        """
        logger.info(f"Executing cohort: {defn.name}")
        attrition = []

        all_patients = self._query(f"SELECT DISTINCT person_id FROM {self.schema}.person")
        attrition.append({"step": "All patients in database", "count": len(all_patients), "excluded": 0})

        index_patients = self._first_event_dates(defn.index_domain, defn.index_concept_ids)
        index_patients = index_patients.rename(columns={"first_event_date": "index_date"})
        attrition.append({
            "step": f"Has {defn.index_domain.lower()} event ({', '.join(defn.index_terms)})",
            "count": len(index_patients),
            "excluded": len(all_patients) - len(index_patients),
        })

        if not defn.outcome_domain:
            final = index_patients
        else:
            outcome_patients = self._first_event_dates(
                defn.outcome_domain, defn.outcome_concept_ids, index_patients["person_id"].tolist()
            )
            outcome_patients = outcome_patients.rename(columns={"first_event_date": "outcome_date"})
            attrition.append({
                "step": f"Also has {defn.outcome_domain.lower()} event ({', '.join(defn.outcome_terms)})",
                "count": len(outcome_patients),
                "excluded": len(index_patients) - len(outcome_patients),
            })

            merged = index_patients.merge(outcome_patients, on="person_id", how="inner")
            merged["index_date"] = pd.to_datetime(merged["index_date"])
            merged["outcome_date"] = pd.to_datetime(merged["outcome_date"])
            merged["days_between"] = (merged["outcome_date"] - merged["index_date"]).dt.days

            if defn.require_index_first:
                temporal_match = merged[
                    (merged["days_between"] >= 0) & (merged["days_between"] <= defn.temporal_window_days)
                ]
            else:
                temporal_match = merged[merged["days_between"].abs() <= defn.temporal_window_days]

            attrition.append({
                "step": f"Within {defn.temporal_window_days}-day window",
                "count": len(temporal_match),
                "excluded": len(merged) - len(temporal_match),
            })
            final = temporal_match

        final = self._apply_age_filter(final, defn.min_age, defn.max_age, attrition)

        result = CohortResult(definition=defn, members=final, attrition=attrition, total_count=len(final))
        logger.info(f"Cohort '{defn.name}': {result.total_count:,} members")
        return result

    def _apply_age_filter(
        self, members: pd.DataFrame, min_age: int | None, max_age: int | None,
        attrition: list[dict], as_of_year: int | None = None,
    ) -> pd.DataFrame:
        if min_age is None and max_age is None:
            return members
        if members.empty:
            attrition.append({"step": f"Age {min_age or '*'}-{max_age or '*'}", "count": 0, "excluded": 0})
            return members

        person_list = ",".join(str(p) for p in members["person_id"].tolist()[:10000])
        demo = self._query(f"SELECT person_id, year_of_birth FROM {self.schema}.person WHERE person_id IN ({person_list})")
        reference_year = as_of_year or datetime.now(tz=timezone.utc).year
        demo["age"] = reference_year - demo["year_of_birth"]
        if min_age is not None:
            demo = demo[demo["age"] >= min_age]
        if max_age is not None:
            demo = demo[demo["age"] <= max_age]

        filtered = members[members["person_id"].isin(demo["person_id"])]
        attrition.append({
            "step": f"Age {min_age or '*'}-{max_age or '*'}",
            "count": len(filtered),
            "excluded": len(members) - len(filtered),
        })
        return filtered

    def execute_escalation(
        self,
        name: str,
        drug_ladder_terms: list[str],
        window_days: int = 180,
        min_age: int | None = None,
        max_age: int | None = None,
    ) -> CohortResult:
        """Patients whose prescriptions moved up an ordered potency ladder.

        drug_ladder_terms is weakest-to-strongest (e.g. codeine, hydrocodone,
        oxycodone, fentanyl). A patient qualifies if they have at least two
        rungs of the ladder, in increasing order, with the last rung's start
        date within window_days of the first rung to appear.
        """
        logger.info(f"Executing escalation cohort: {name}")
        attrition = []

        all_patients = self._query(f"SELECT DISTINCT person_id FROM {self.schema}.person")
        attrition.append({"step": "All patients in database", "count": len(all_patients), "excluded": 0})

        rung_dates = []
        for rung, term in enumerate(drug_ladder_terms):
            concept_ids = self._resolve_concepts("Drug", [term])
            if not concept_ids:
                logger.warning(f"  No concepts resolved for ladder term '{term}' — skipping rung")
                continue
            dates = self._first_event_dates("Drug", concept_ids)
            dates["rung"] = rung
            dates["drug_term"] = term
            rung_dates.append(dates.rename(columns={"first_event_date": "rung_date"}))

        if len(rung_dates) < 2:
            raise ValueError("execute_escalation needs at least two resolvable ladder terms")

        all_rungs = pd.concat(rung_dates, ignore_index=True)
        all_rungs["rung_date"] = pd.to_datetime(all_rungs["rung_date"])

        distinct_rungs = all_rungs.groupby("person_id")["rung"].nunique()
        patients_with_any = set(all_rungs["person_id"].unique())
        attrition.append({
            "step": "Has any ladder drug",
            "count": len(patients_with_any),
            "excluded": len(all_patients) - len(patients_with_any),
        })

        multi_rung_patients = set(distinct_rungs[distinct_rungs >= 2].index)
        attrition.append({
            "step": "Has 2+ distinct ladder rungs",
            "count": len(multi_rung_patients),
            "excluded": len(patients_with_any) - len(multi_rung_patients),
        })

        escalated = []
        candidates = all_rungs[all_rungs["person_id"].isin(multi_rung_patients)]
        for person_id, group in candidates.groupby("person_id"):
            group = group.sort_values("rung")
            first_date = group["rung_date"].min()
            last_row = group.loc[group["rung"].idxmax()]
            span_days = (last_row["rung_date"] - first_date).days
            if last_row["rung"] > 0 and 0 <= span_days <= window_days:
                escalated.append({
                    "person_id": person_id,
                    "first_rung": int(group["rung"].min()),
                    "highest_rung": int(last_row["rung"]),
                    "span_days": span_days,
                })

        final = pd.DataFrame(escalated) if escalated else pd.DataFrame(columns=["person_id"])
        attrition.append({
            "step": f"Escalated within {window_days} days",
            "count": len(final),
            "excluded": len(multi_rung_patients) - len(final),
        })

        final = self._apply_age_filter(final, min_age, max_age, attrition)

        definition = CohortDefinition(
            name=name, description=f"Opioid escalation across {drug_ladder_terms} within {window_days} days",
            index_domain="Drug", index_terms=drug_ladder_terms,
            temporal_window_days=window_days, min_age=min_age, max_age=max_age,
        )
        result = CohortResult(definition=definition, members=final, attrition=attrition, total_count=len(final))
        logger.info(f"Cohort '{name}': {result.total_count:,} members")
        return result

    def execute_concurrent_drug_count(
        self,
        name: str,
        min_concurrent_drugs: int,
        min_age: int | None = None,
        max_age: int | None = None,
    ) -> CohortResult:
        """Patients whose distinct active drugs peaked at min_concurrent_drugs
        or more at some point in their history.

        Polypharmacy isn't "on N drugs on one specific calendar date" — real
        phenotype definitions ask whether a person was ever managing that
        many medications at once, which is a peak-concurrency question, not
        a point-in-time one. Anchoring to a single reference date (the
        population's max drug_exposure_end_date, say) is fragile besides:
        whichever one row happens to hold that extreme value sets the whole
        query, and every other patient's polypharmacy is measured against a
        date that has nothing to do with their own timeline. This uses the
        standard sweep-line approach instead: a +1 event at each exposure's
        start and a -1 event the day after it ends, a running sum per person
        in date order, and that running total's maximum is the person's own
        peak concurrent drug count — independent of anyone else's dates.
        """
        logger.info(f"Executing concurrent-drug-count cohort: {name}")
        attrition = []

        all_patients = self._query(f"SELECT DISTINCT person_id FROM {self.schema}.person")
        attrition.append({"step": "All patients in database", "count": len(all_patients), "excluded": 0})

        peak_concurrency = self._query(
            f"""
            WITH events AS (
                SELECT person_id, drug_exposure_start_date AS event_date, 1 AS delta
                FROM {self.schema}.drug_exposure
                UNION ALL
                SELECT person_id, drug_exposure_end_date + INTERVAL '1 day' AS event_date, -1 AS delta
                FROM {self.schema}.drug_exposure
            ),
            running AS (
                -- delta ASC breaks a same-day tie by applying the -1 (an
                -- exposure ending) before the +1 (the next one starting): a
                -- drug that ends 2020-01-31 and the next that starts
                -- 2020-02-01 don't share a day of overlap, so the first
                -- has to be counted as already gone before the second is
                -- counted as arrived, not the other way around.
                SELECT
                    person_id,
                    SUM(delta) OVER (
                        PARTITION BY person_id ORDER BY event_date, delta ASC
                        ROWS UNBOUNDED PRECEDING
                    ) AS concurrent_count
                FROM events
            )
            SELECT person_id, MAX(concurrent_count) AS peak_concurrent_drugs
            FROM running
            GROUP BY person_id
            """
        )
        attrition.append({
            "step": "Has any drug exposure",
            "count": len(peak_concurrency),
            "excluded": len(all_patients) - len(peak_concurrency),
        })

        qualifying = peak_concurrency[peak_concurrency["peak_concurrent_drugs"] >= min_concurrent_drugs]
        attrition.append({
            "step": f"Peak {min_concurrent_drugs}+ concurrent drugs",
            "count": len(qualifying),
            "excluded": len(peak_concurrency) - len(qualifying),
        })

        final = self._apply_age_filter(qualifying, min_age, max_age, attrition)

        definition = CohortDefinition(
            name=name,
            description=f"Peak {min_concurrent_drugs}+ concurrently active drugs",
            index_domain="Drug", index_terms=[f"{min_concurrent_drugs}+ concurrent"],
            min_age=min_age, max_age=max_age,
        )
        result = CohortResult(definition=definition, members=final, attrition=attrition, total_count=len(final))
        logger.info(f"Cohort '{name}': {result.total_count:,} members")
        return result

    def attrition_dataframe(self, result: CohortResult) -> pd.DataFrame:
        """Convert attrition data to a DataFrame for visualization."""
        return pd.DataFrame(result.attrition)
