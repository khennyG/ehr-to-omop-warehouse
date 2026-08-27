# The official apache/airflow image has neither this project's own Python
# dependencies (pandas, sqlalchemy, great-expectations, ...) nor dbt — both are
# things the DAG's tasks shell out to (`python -m src.main`, `dbt build`), so
# both have to live inside the container the scheduler and webserver actually run
# in, not just in the local dev venv this repo's README tells a contributor to
# create on their own machine.
FROM apache/airflow:2.7.3-python3.10

COPY requirements.txt /tmp/requirements.txt

# apache-airflow itself is already satisfied by the base image; installing it
# again from requirements.txt here would fight the base image's own pinned
# constraint set. Every other line in requirements.txt is fair game.
RUN pip install --no-cache-dir --user \
    $(grep -v -E '^\s*(#|apache-airflow)' /tmp/requirements.txt | grep -v '^\s*$')
