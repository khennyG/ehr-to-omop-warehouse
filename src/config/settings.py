"""Centralized configuration loaded from environment variables.

All paths, credentials, and tuning parameters live here. Nothing is
hardcoded in the pipeline modules — they import from this module.
"""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings populated from .env or environment variables."""

    # ── Warehouse backend ──
    # "duckdb" runs the pipeline against a local, embedded DuckDB file — no
    # infrastructure to stand up, which is what makes the demo data path in
    # scripts/generate_demo_data.py runnable anywhere Python is installed. "postgres"
    # is the documented production target: the schema in sql/schema/ and the
    # docker-compose stack are both built for it. Both paths run the exact same
    # SQLAlchemy code in src/load, src/quality, and src/analytics — only the
    # connection string changes.
    warehouse_backend: str = "duckdb"
    duckdb_path: Path = Path("./data/processed/omop_demo.duckdb")

    # ── Database (postgres backend) ──
    postgres_user: str = "omop"
    postgres_password: str = "omop_dev"
    postgres_db: str = "omop_cdm"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # ── Paths ──
    project_root: Path = Path(__file__).resolve().parents[2]
    synthea_output_dir: Path = Path("./data/raw/synthea")
    vocabulary_dir: Path = Path("./data/vocabularies")
    processed_dir: Path = Path("./data/processed")

    # ── Pipeline ──
    synthea_population: int = 10_000
    log_level: str = "INFO"
    batch_size: int = 50_000

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def database_url(self) -> str:
        if self.warehouse_backend == "duckdb":
            self.duckdb_path.parent.mkdir(parents=True, exist_ok=True)
            return f"duckdb:///{self.duckdb_path}"
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
