# 0003: Full OMOP v5.4 schema, partially populated

**Status:** Accepted

## Context

The transform pipeline populates nine clinical tables: `person`,
`observation_period`, `visit_occurrence`, `condition_occurrence`, `drug_exposure`,
`procedure_occurrence`, `measurement`, `observation`, `death`. The real OMOP CDM v5.4
defines 37 tables — vocabulary tables, health system tables (`location`,
`care_site`, `provider`), health economics (`payer_plan_period`, `cost`),
standardized derived elements (`drug_era`, `dose_era`, `condition_era`), cohort
tables, `note` / `note_nlp`, `specimen`, `fact_relationship`, `device_exposure`,
`visit_detail`. Writing DDL only for the nine tables the pipeline actually fills
would have been less work and would have matched what's populated exactly.

## Decision

`sql/schema/01_ddl.sql` defines the full 37-table schema, correctly keyed
(`02_primary_keys.sql`), constrained (`03_constraints.sql`), and indexed
(`04_indices.sql`) — not just the nine tables with data in them. The unpopulated
ones carry a comment block in `01_ddl.sql` explaining they're real, correctly-built,
and simply not fed by this pipeline yet.

The reasoning is about the audience this project is for. Someone evaluating this who
already knows OMOP — someone who's worked with `condition_era` or `fact_relationship`
before — will notice immediately if the schema stops at the tables that happen to be
populated. A half-schema reads as "doesn't know the full model," even if every table
that *is* there is done correctly. A full schema with an honest note about what's
populated reads as "knows the model, is transparent about current scope" — which is
the more accurate description of where this project actually is.

This mirrors OHDSI's own DDL convention directly: a separate `ddl.sql` /
`primary_keys.sql` / `constraints.sql` / `indices.sql` split (data loads before
constraints exist, constraints get added once the tables are populated), which is
also why the files here are numbered — docker-compose mounts `sql/schema/` into
`/docker-entrypoint-initdb.d`, and Postgres runs every file it finds there in
whatever order the filenames sort into.

## Alternatives considered

**Schema matching exactly what's populated (9 tables).** Less code, and arguably more
honest in the narrowest sense — no table exists that isn't used. I moved away from
this because it understates the model itself, not just this pipeline's current
coverage of it; OMOP CDM v5.4 *is* a 37-table model, and representing it as 9 tables
misrepresents the standard, not just the project.

**Full schema, but skip the vocabulary tables' internal foreign keys** (`concept` →
`domain`, `concept_relationship` → `concept`, and so on) since only `concept` and
`concept_relationship` are directly queried by the pipeline. Rejected — those
relationships are part of what makes the vocabulary tables function as a coherent
whole rather than a loose pile of CSVs, and getting them right is exactly the kind of
detail that signals real familiarity with the model. (This did surface a real
bootstrap problem: `concept.domain_id → domain.domain_id` and
`domain.domain_concept_id → concept.concept_id` are circular, and no load order
satisfies both directions as enforced constraints on first insert. The fix — not
enforcing the metadata-points-back-at-itself direction, since the load order this
pipeline uses only needs the other one — is documented directly in
`03_constraints.sql`.)

## Consequences

A reviewer who knows OMOP can check this schema against the real spec and find it
matches, table for table, column for column. The tradeoff is that a chunk of this
schema is genuinely idle right now — `note`, `specimen`, `device_exposure`, and the
rest sit empty, which is future work, not a demonstration of something already
working. That's stated plainly in the DDL's own comments rather than left for
someone to discover by querying an empty table and wondering if something's broken.
