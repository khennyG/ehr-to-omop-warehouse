# 0002: dbt builds a second, independent copy of the OMOP transform

**Status:** Accepted

## Context

The project's build plan calls for a dbt layer with staging, intermediate, and mart
models producing "final OMOP CDM tables." Taken literally, that means dbt building
`person`, `condition_occurrence`, `drug_exposure`, and the rest — the same tables
`src/transform/omop_transformer.py` already builds in Python. Two implementations of
the same transform, writing to the same place, is a real operational hazard: dbt
marts are `+materialized: table`, meaning a `dbt run` drops and rebuilds every table
it touches from its own SQL. Point that at the `cdm` schema the Python pipeline
already owns and every `dbt run` silently discards whatever the Python pipeline just
loaded — two writers racing for the same tables, with whichever ran last winning.

## Decision

dbt's marts target a separate schema, `cdm_dbt`, not `cdm` — set via
`dbt_project.yml`'s `+schema: cdm_dbt` and a `generate_schema_name` macro override so
dbt doesn't prefix it into something like `dbt_staging_cdm_dbt` by default. `cdm`
stays exclusively owned by `src/load/warehouse_loader.py`. dbt's own vocabulary
lookups read `cdm.concept` / `cdm.concept_relationship` as a **source** — data it
reads but never writes, populated by `load_vocabulary()` in the Python pipeline —
which is what makes the SQL-side "Maps to" resolution in
`dbt/models/intermediate/int_conditions_mapped.sql` and friends match
`VocabularyMapper.to_standard()`'s in-memory version exactly, not just approximately.

Positioning this as **two independent implementations of the same transform** rather
than "dbt implements it, Python doesn't really need to" turns dbt's own test suite
into something more useful than a syntax check: if the Python pipeline and the dbt
build ever disagree on `cdm.person` vs `cdm_dbt.person`, that's a real finding about
one of the two implementations being wrong, not a merge conflict to resolve by
picking one and deleting the other. I checked this directly after both were built:
every table both sides produce — `person`, `visit_occurrence`,
`condition_occurrence`, `drug_exposure`, `measurement` — has identical row counts
against the same demo warehouse.

## Alternatives considered

**Have dbt read from `cdm.*` (the Python pipeline's tables) and only add tests on
top, no new mart models.** This is closer to what the README originally described
("dbt then runs a second pass of data tests") before I built the mart layer out.
I moved past it because it undersells what dbt actually demonstrates — a SQL-native
implementation of vocabulary resolution and surrogate-key generation is a real,
separate skill from writing dbt tests against someone else's tables, and the build
plan itself asks for staging/intermediate/mart models, not just a test suite.

**Have the Python pipeline stop loading `cdm` directly and read from `cdm_dbt`
instead — dbt as the only writer.** Rejected because it would make the Python
pipeline non-functional without a dbt run first, defeating the point of
`python -m src.main --stage all` working standalone (see ADR 0001), and because the
Python-side transform logic — the vocabulary mapper, the surrogate-key generation,
the cohort engine — is the part of this project I most want a reviewer to actually
read.

## Consequences

Running `dbt build` against the docker-compose Postgres target and running
`python -m src.main --stage load` against the same database produces two complete,
independently-built copies of the core OMOP tables, in two schemas. That's more
storage than a single-writer design, and it means anyone extending this project has
to decide, for a new table, whether it belongs in one implementation or both — a
real cost, taken on deliberately for what the comparison is worth.
