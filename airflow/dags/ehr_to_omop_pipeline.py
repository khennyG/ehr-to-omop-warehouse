"""Orchestrates the EHR-to-OMOP pipeline: extract, transform, load, quality, dbt.

Each stage is a separate task running `python -m src.main --stage <name>` —
the same CLI a developer runs by hand locally, not a reimplementation of the
pipeline logic in Airflow-specific code. That's deliberate: the DAG's job is
sequencing and retries, not owning business logic a second time.

quality is a real gate, not just a status report. src/main.py's quality stage
calls sys.exit(1) when a DQD check marked CRITICAL fails, which fails this
task and stops the DAG before dbt_build runs — there's no point cross-checking
against dbt's independent build of the same tables if the warehouse itself
already failed its own conformance checks.

schedule is None: this pipeline processes a fixed synthetic population, not
data that arrives on its own on a schedule. Triggering it is a deliberate
action (a new demo population, a vocabulary refresh), not something that
should happen unattended at 2am.
"""

from datetime import datetime, timedelta

from airflow.operators.bash import BashOperator

from airflow import DAG

default_args = {
    "owner": "data-engineering",
    "depends_on_past": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=5),
}

with DAG(
    dag_id="ehr_to_omop_pipeline",
    description="Synthea -> OMOP CDM v5.4: extract, transform, load, quality, dbt",
    default_args=default_args,
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["omop", "etl", "healthcare"],
) as dag:

    extract = BashOperator(
        task_id="extract",
        bash_command="cd /opt/airflow && python -m src.main --stage extract",
    )

    transform = BashOperator(
        task_id="transform",
        bash_command="cd /opt/airflow && python -m src.main --stage transform",
    )

    load = BashOperator(
        task_id="load",
        bash_command="cd /opt/airflow && python -m src.main --stage load",
    )

    quality = BashOperator(
        task_id="quality",
        bash_command="cd /opt/airflow && python -m src.main --stage quality",
    )

    dbt_build = BashOperator(
        task_id="dbt_build",
        bash_command="cd /opt/airflow/dbt && dbt build --profiles-dir . --target prod",
    )

    extract >> transform >> load >> quality >> dbt_build
