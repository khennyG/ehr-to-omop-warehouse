# 0001: Local DuckDB backend alongside the Postgres/Docker production path

**Status:** Accepted

## Context

The documented production path for this project is Postgres via docker-compose, with
Airflow orchestrating it — that's what `sql/schema/` is written for, and what a real
deployment would run. But I built this without Docker or a local Postgres instance
running, and I wanted the pipeline to actually execute, not just look correct on
paper. A portfolio project that's never been run end to end is a bet that nothing's
wrong with it, and I didn't want to make that bet.

## Decision

`src/config/settings.py` gets a `warehouse_backend` field — `duckdb` by default,
`postgres` when set explicitly (docker-compose sets it). Every module that talks to
the warehouse (`warehouse_loader.py`, `dqd_checks.py`, `cohort_builder.py`) goes
through SQLAlchemy against whichever backend `database_url` resolves to. DuckDB is an
embedded, zero-install database — no server, no container, just a file — so the whole
pipeline runs on a bare Python install.

This wasn't free. Two real incompatibilities showed up once I actually ran it:

- DuckDB doesn't support `ALTER TABLE ... ADD CONSTRAINT ... FOREIGN KEY` — verified
  directly, every one of `03_constraints.sql`'s statements fails on it with "No
  support for that ALTER TABLE option yet!" The demo backend runs without enforced
  foreign keys as a result. Postgres is what actually holds the schema to its real
  constraints; `01_ddl.sql`, `02_primary_keys.sql`, and `04_indices.sql` all apply
  cleanly to both.
- `to_sql()`'s executemany-style insert is fine against Postgres but roughly 470x
  slower against DuckDB than DuckDB's own way of taking a DataFrame — measured
  directly, a 400,000-row frame took 43.6 seconds one way and 0.09 seconds the other.
  `src/db_utils.py` picks the fast path per-backend rather than using `to_sql()`
  everywhere for consistency's sake.

## Alternatives considered

**SQLite instead of DuckDB.** Also embedded and zero-install, but no native
DataFrame-loading path (the whole reason DuckDB's bulk-insert is fast) and weaker
SQL support for the window-function-heavy queries `cohort_builder.py` uses (the
polypharmacy cohort's peak-concurrency logic is a sweep-line built on
`SUM(...) OVER (... ROWS UNBOUNDED PRECEDING)`).

**Mocking the database in tests instead of a real backend.** Would have avoided the
DuckDB-specific incompatibilities entirely, but at the cost of never actually
verifying the SQL runs — and the incompatibilities above are exactly the kind of
thing a mock would have hidden. `tests/test_warehouse_loader.py` and
`tests/test_cohort_builder.py` both run against a real, temporary DuckDB file for
this reason.

**Skip local execution, document a "run against Postgres" instruction and ship
untested.** This is what I moved away from. I'd rather ship a project where I can
say every stage of it actually ran, on real (synthetic) data, than one that reads
correctly but was never executed.

## Consequences

Anyone cloning this repo can run the full pipeline — `python -m src.main --stage
all` — without installing anything beyond `pip install -r requirements.txt`. The
tradeoff is that the demo path and the production path aren't byte-identical: the
demo warehouse doesn't get real foreign-key enforcement, so referential integrity
there is checked by `tests/test_integration_pipeline.py` instead of the database
itself. That's a real gap between demo and production, and it's a deliberate one —
Postgres is where I want that constraint actually enforced by the engine, not
somewhere I quietly weakened it to make the demo path easier.
