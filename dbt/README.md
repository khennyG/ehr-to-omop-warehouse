# dbt layer

This directory is a second, independent implementation of the OMOP transform — the
same job `src/transform/omop_transformer.py` does in pandas, done again here in SQL.
That's a deliberate choice, not duplication for its own sake: dbt gives this pipeline
declarative dependency graphs, a real test framework (`dbt test`), and generated
documentation (`dbt docs`) for free, and having two implementations of the same
transform means dbt's tests function as an independent check on the Python pipeline's
output. When both agree, that's real evidence the transform logic is right, not just
that one code path is internally consistent with itself.

Run `dbt build` from this directory (`cd dbt && dbt build --profiles-dir .`) and it
reads the same `stg_*` tables the Python pipeline's extract stage already loaded,
resolves vocabulary the same way `VocabularyMapper` does — by joining against
`cdm.concept` / `cdm.concept_relationship`, populated by
`src/load/warehouse_loader.py`'s `load_vocabulary()`, not by dbt — and writes its own
OMOP tables into a `cdm_dbt` schema, deliberately separate from `cdm`. `cdm` is what
the Python pipeline owns; a `+materialized: table` dbt run drops and rebuilds
everything it touches on every invocation, so pointing it at the same schema as a
live pipeline would mean two writers fighting over the same tables. See the comment
at the top of `dbt_project.yml` for the full reasoning.

Both paths run against the same 3,000-patient demo population and produce the same
row counts for the tables both sides build (compared directly against the real demo
warehouse: person, visit_occurrence, condition_occurrence, drug_exposure, and
measurement all match exactly). Everything type-cast in `models/staging/` mirrors
what `src/extract/synthea_loader.py` validates; everything in `models/marts/` mirrors
a function in `omop_transformer.py`.

## What's here and what isn't

| Domain | Python (`src/transform/`) | dbt (`models/marts/`) |
|---|---|---|
| person | `transform_person` | `person.sql` |
| visit_occurrence | `transform_visit_occurrence` | `visit_occurrence.sql` |
| condition_occurrence | `transform_condition_occurrence` | `condition_occurrence.sql` |
| drug_exposure | `transform_drug_exposure` | `drug_exposure.sql` |
| measurement | `transform_measurement` | `measurement.sql` |
| observation_period | `transform_observation_period` | not yet ported |
| procedure_occurrence | `transform_procedure_occurrence` | not yet ported |
| observation (text-valued) | `transform_observation` | not yet ported |
| death | `transform_death` | not yet ported |

The five domains built here are the ones with the clearest vocabulary-mapping
story to demonstrate in SQL. The other four are Python-only for now — porting them
is mechanical, not blocked on anything, just not done yet.

## Layout

- `models/staging/` — 1:1 typed mirrors of the six Synthea source tables, materialized
  as views. Reads from the `synthea` source (the `stg_*` tables extract loads —
  `main` on the DuckDB dev target, `public` on Postgres; see the Jinja in
  `models/staging/schema.yml`, since the two backends don't share a default schema
  name).
- `models/intermediate/` — vocabulary resolution: a source code and a standard
  concept_id, joined off `cdm.concept` / `cdm.concept_relationship` the same way
  `VocabularyMapper.resolve()` does in memory. `int_conditions_mapped` also
  deduplicates — Synthea occasionally emits the same condition twice for one
  encounter.
- `models/marts/` — the OMOP tables themselves, materialized as tables in `cdm_dbt`.

## Running it

```bash
cd dbt
dbt build --profiles-dir .          # local DuckDB target (dev) — the default
dbt build --profiles-dir . --target prod   # docker-compose Postgres
```

`dev` needs the Python pipeline's extract stage to have run first (`python -m
src.main --stage extract` from the repo root) — that's what populates the `stg_*`
tables this project's sources point at. It also needs `load_vocabulary()` to have run
(part of `--stage load`) so `cdm.concept` has something in it to join against.
