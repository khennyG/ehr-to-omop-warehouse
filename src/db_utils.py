"""Shared bulk-write helper used by both the extract and load stages.

pandas' DataFrame.to_sql goes through the DBAPI's executemany path no matter
which method= is passed — every row, or row-batch, becomes its own INSERT
statement. That's a reasonable way to talk to Postgres, whose driver batches
it efficiently, but it's roughly 450x slower against DuckDB than the way
DuckDB is actually meant to be given a DataFrame: register it as a virtual
view and let DuckDB's own vectorized engine read directly from it. Measured
directly — a 400,000-row frame took 43.6s via to_sql(method="multi") and
0.09s via register-and-SELECT. Both src/extract/synthea_loader.py and
src/load/warehouse_loader.py write tables at exactly this scale (this
project's demo population produces a 400,000+ row observations table on its
own), so both go through this instead of calling to_sql directly.
"""

import pandas as pd
from sqlalchemy.engine import Engine

from src.config.settings import settings


def bulk_write(
    df: pd.DataFrame,
    table_name: str,
    engine: Engine,
    schema: str | None = None,
    if_exists: str = "append",
) -> None:
    """Write a DataFrame to a table, fast, on either backend.

    if_exists="replace" drops and recreates the table from the DataFrame's
    own inferred schema — right for staging tables, which have no schema of
    their own to begin with. if_exists="append" inserts into a table that
    already exists with its own schema and constraints — right for OMOP
    tables, which sql/schema/ built with real primary and foreign keys that
    "replace" would silently strip away.
    """
    full_name = f"{schema}.{table_name}" if schema else table_name

    if engine.dialect.name == "duckdb":
        raw = engine.raw_connection()
        try:
            con = raw.driver_connection
            assert con is not None, "engine.raw_connection() returned a connection with no driver_connection"
            con.register("_bulk_write_df", df)
            if if_exists == "replace":
                con.execute(f"CREATE OR REPLACE TABLE {full_name} AS SELECT * FROM _bulk_write_df")
            else:
                # Named, not positional: an OMOP table like person has more
                # columns (location_id, provider_id, ...) than any single
                # transform function populates, so a plain `SELECT *` would
                # either miscount or silently shift values into the wrong
                # columns. Naming both sides inserts each DataFrame column
                # into its matching table column and leaves the rest NULL.
                columns = ", ".join(df.columns)
                con.execute(f"INSERT INTO {full_name} ({columns}) SELECT {columns} FROM _bulk_write_df")
            con.unregister("_bulk_write_df")
            raw.commit()
        finally:
            raw.close()
    else:
        df.to_sql(
            table_name, engine, schema=schema, if_exists=if_exists,
            index=False, method="multi", chunksize=settings.batch_size,
        )
