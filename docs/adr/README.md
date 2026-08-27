# Architecture decision records

Short records of the decisions in this project that weren't obvious calls —
places where there was a real alternative on the table and I picked one
deliberately. Not a changelog and not a design spec; just the reasoning
behind the choices that would otherwise only live in my own head or in a
commit message nobody reads six months later.

| ADR | Decision |
|---|---|
| [0001](0001-dual-warehouse-backend.md) | Local DuckDB backend alongside the documented Postgres/Docker production path |
| [0002](0002-dbt-independent-implementation.md) | dbt builds a second, independent copy of the OMOP transform, not a shared writer |
| [0003](0003-full-omop-ddl-partial-population.md) | Full OMOP v5.4 schema, partially populated, rather than a trimmed-down schema |
| [0004](0004-synthetic-demo-data-and-vocabulary.md) | A synthetic demo population and vocabulary seed, not a placeholder-only repo |
| [0005](0005-generalized-cohort-engine.md) | A domain-agnostic cohort engine instead of three separate cohort implementations |
