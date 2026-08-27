"""The three phenotype definitions this project reports on, as concrete
parameters over the three execution shapes in cohort_builder.py.

Keeping the catalog separate from the engine is deliberate: cohort_builder.py
answers "how do you execute a temporal phenotype against OMOP data" in
general, and this module answers "what specifically counts as
diabetes_complications" — a clinical judgment call, not an engineering one.
Someone auditing whether these definitions are clinically reasonable should
be able to read this file without wading through SQL construction to do it.

Every function takes a CohortBuilder and returns a CohortResult, so all three
compose the same way with the rest of the analytics layer (attrition tables,
the notebooks in notebooks/).
"""

from src.analytics.cohort_builder import CohortBuilder, CohortResult

# Matches the cardiovascular outcome codes in scripts/demo_codes.py
# (CONDITION_MI, CONDITION_STROKE, CONDITION_HEART_FAILURE, CONDITION_CAD) —
# any one of these within a year of a T2DM diagnosis counts as a complication.
CARDIOVASCULAR_EVENT_TERMS = [
    "myocardial infarction", "cerebrovascular accident", "heart failure", "coronary arteriosclerosis",
]

# Weakest to strongest, matching scripts/demo_codes.py's OPIOID_LADDER.
OPIOID_LADDER_TERMS = ["codeine", "hydrocodone", "oxycodone", "fentanyl"]


def diabetes_complications(builder: CohortBuilder) -> CohortResult:
    """T2DM patients with a cardiovascular event within a year of diagnosis.

    Condition -> condition, not drug -> condition: metformin would catch
    most T2DM patients too, but it's a proxy for the diagnosis, not the
    diagnosis itself, and this phenotype is specifically about outcomes
    following diagnosis.
    """
    defn = builder.define(
        name="diabetes_complications",
        index_domain="Condition", index_terms=["diabetes"],
        outcome_domain="Condition", outcome_terms=CARDIOVASCULAR_EVENT_TERMS,
        temporal_window_days=365,
        require_index_first=True,
    )
    return builder.execute(defn)


def opioid_escalation(builder: CohortBuilder) -> CohortResult:
    """Patients whose opioid prescriptions moved up the potency ladder
    within six months."""
    return builder.execute_escalation(
        name="opioid_escalation",
        drug_ladder_terms=OPIOID_LADDER_TERMS,
        window_days=180,
    )


def polypharmacy_elderly(builder: CohortBuilder) -> CohortResult:
    """Patients 65+ whose active prescriptions peaked at five or more at once."""
    return builder.execute_concurrent_drug_count(
        name="polypharmacy_elderly",
        min_concurrent_drugs=5,
        min_age=65,
    )


PREDEFINED_COHORTS = {
    "diabetes_complications": diabetes_complications,
    "opioid_escalation": opioid_escalation,
    "polypharmacy_elderly": polypharmacy_elderly,
}


def run_all(builder: CohortBuilder) -> dict[str, CohortResult]:
    """Execute every predefined cohort and return them by name."""
    return {name: fn(builder) for name, fn in PREDEFINED_COHORTS.items()}
