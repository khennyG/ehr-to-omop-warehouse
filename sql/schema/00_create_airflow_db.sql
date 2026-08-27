-- Airflow's own metadata (DAG runs, task instances, connections) needs a
-- database of its own — mixing it into the omop_cdm database POSTGRES_DB
-- already creates would put Airflow's internal tables in the same
-- namespace as the OMOP CDM schema this project is actually about. This
-- file is numbered to run before 01_ddl.sql for the same reason every file
-- in this directory is numbered: docker-compose mounts sql/schema/ into
-- /docker-entrypoint-initdb.d, and Postgres runs every file it finds there
-- in whatever order the filenames sort into.
create database airflow;
