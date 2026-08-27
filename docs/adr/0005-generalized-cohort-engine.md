# 0005: A domain-agnostic cohort engine, not three separate cohort implementations

**Status:** Accepted

## Context

The three predefined cohorts this project reports on — `diabetes_complications`,
`opioid_escalation`, `polypharmacy_elderly` — turned out to be three genuinely
different shapes of temporal logic, not one pattern with different parameters:

- **diabetes_complications** is an index event followed by an outcome event within a
  window. The original `CohortBuilder` only supported this shape for drug → condition
  specifically (its own module docstring's example was `metformin` → `lactic
  acidosis`) — but this phenotype is condition → condition (a T2DM diagnosis followed
  by a cardiovascular event), which the drug-specific version couldn't express at all.
- **opioid_escalation** isn't a two-point comparison — it's a sequence climbing an
  ordered potency ladder (codeine → hydrocodone → oxycodone → fentanyl), which needs
  to know about *order*, not just presence and a date.
- **polypharmacy_elderly** has no "first this, then that" story whatsoever. It's a
  count of how many distinct drugs were active *at the same time*, which is a
  date-range overlap question, not a temporal-sequence question.

## Decision

Rather than write three separate cohort functions, `CohortBuilder` got three
general-purpose execution methods, each one built to answer a class of question, and
`src/analytics/predefined_cohorts.py` wires concrete parameters onto them:

- `execute()` — generalized from drug-then-condition to **any pair of clinical
  domains**. `DOMAIN_TABLES` maps `"Condition"` and `"Drug"` to their table/column
  names, and `_resolve_concepts()` takes a *list* of search terms and unions the
  matches, since a real outcome like "a cardiovascular event" is several conditions
  (myocardial infarction, stroke, heart failure, coronary arteriosclerosis), not one.
- `execute_escalation()` — a potency ladder as an ordered list of search terms;
  qualifies a patient if two or more rungs appear with the highest one reached within
  the window.
- `execute_concurrent_drug_count()` — the interesting one. My first version anchored
  to a single reference date (the population's max `drug_exposure_end_date`) and
  checked who had N+ drugs active on that one day — which is fragile in a way that
  isn't obvious until you run it: whichever single row happens to hold that extreme
  value sets the whole query, and it returned almost no one, twice, for two different
  reasons (see below). The actual fix is a proper peak-concurrency calculation: a
  standard sweep-line, a +1 event at each exposure's start and a -1 event the day
  after it ends, a running sum per person in date order via
  `SUM(delta) OVER (PARTITION BY person_id ORDER BY event_date, delta ASC ROWS
  UNBOUNDED PRECEDING)`, and that running total's maximum is the person's own peak —
  independent of anyone else's dates entirely.

## What actually went wrong building the third one

Worth being specific about, since "it works now" undersells how non-obvious the
fix was. The single-reference-date version returned close to zero members even after
I'd already fixed the reference date's fragility, because of a *second*, unrelated
bug: `drug_exposure_end_date` for a still-open prescription was falling back to its
own start date (a one-day exposure) rather than a duration reflecting how long the
prescription had actually been running — which I only caught by checking the real
distribution of computed end dates against what I expected. Fixing that meant
`DISPENSES` (fill count) needed to drive a real multi-refill duration estimate
(`dispenses × 30 days`), and `scripts/generate_demo_data.py`'s chronic-medication
logic needed a `dispenses` count that actually scales with elapsed time, not a fixed
default. Even after both of those fixes, the sweep-line's first version still had an
off-by-one tie-break bug: two exposures ending and starting on the same calendar day
were briefly counted as overlapping when they weren't, caught by a test built
specifically for that boundary case
(`test_sequential_drugs_never_count_as_concurrent` in
`tests/test_cohort_builder.py`).

## Alternatives considered

**Three separate, purpose-built functions**, one per cohort, each with hardcoded
logic for exactly its own phenotype. Simpler to write and to reason about in
isolation. Rejected because the three general shapes here — index→outcome across any
domain pair, ordered sequences, peak concurrency — are reusable for phenotypes beyond
these three specific ones, and a reviewer extending this project with a fourth cohort
shouldn't have to write cohort infrastructure from scratch to do it.

## Consequences

Adding a new cohort in the future is a matter of picking which of the three shapes it
fits and supplying parameters, not writing new SQL construction logic. The cost is
that `CohortBuilder` is a less obvious read than three standalone functions would
be — understanding `execute()` means understanding it's domain-agnostic before
understanding what any *one* cohort does with it, which is exactly the tradeoff a
general-purpose engine always makes against three specific ones.
