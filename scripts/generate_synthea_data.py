"""Wrapper around the real Synthea generator, for production use.

scripts/generate_demo_data.py exists because this script needs things a
portfolio reviewer's machine might not have on hand: a JVM, and the several
hundred megabytes of Synthea's own jar and disease modules. Wherever those are
available, this is what actually produces a Synthea population — not a
synthetic stand-in for one, the real generator OHDSI itself points people at.
"""

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import click
from loguru import logger

from src.config.settings import settings

SYNTHEA_JAR_URL = (
    "https://github.com/synthetichealth/synthea/releases/latest/download/"
    "synthea-with-dependencies.jar"
)


def _check_java() -> None:
    if shutil.which("java") is None:
        raise OSError(
            "Java not found on PATH. Synthea requires a JVM (11+) — install one and "
            "re-run, or use scripts/generate_demo_data.py for a Java-free synthetic "
            "population in the meantime."
        )


def _ensure_jar(jar_path: Path) -> None:
    if jar_path.exists():
        return
    logger.info(f"Synthea jar not found at {jar_path} — downloading from {SYNTHEA_JAR_URL}")
    jar_path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(SYNTHEA_JAR_URL, jar_path)
    logger.info(f"Downloaded {jar_path.stat().st_size / 1e6:.0f} MB to {jar_path}")


@click.command()
@click.option(
    "--population", type=int, default=None,
    help="Population size to generate. Defaults to settings.synthea_population.",
)
@click.option("--state", default="Massachusetts", help="US state to generate patients for.")
@click.option("--seed", type=int, default=None, help="Synthea's own random seed, for a reproducible run.")
@click.option(
    "--jar-path", type=click.Path(path_type=Path),
    default=Path("./synthea-with-dependencies.jar"),
    help="Path to the Synthea jar. Downloaded automatically the first time if missing.",
)
@click.option(
    "--output-dir", type=click.Path(path_type=Path), default=None,
    help="Defaults to settings.synthea_output_dir.",
)
def main(population: int | None, state: str, seed: int | None, jar_path: Path, output_dir: Path | None):
    """Run the real Synthea generator and place its CSV export where the
    pipeline's extract stage expects to find it."""
    _check_java()
    _ensure_jar(jar_path)

    n = population or settings.synthea_population
    out = output_dir or settings.synthea_output_dir
    out.mkdir(parents=True, exist_ok=True)

    cmd = [
        "java", "-jar", str(jar_path),
        "-p", str(n),
        f"--exporter.baseDirectory={out.resolve()}",
        "--exporter.csv.export=true",
        "--exporter.csv.folder_per_run=false",
        "--exporter.fhir.export=false",
        "--exporter.hospital.fhir.export=false",
        "--exporter.practitioner.fhir.export=false",
    ]
    if seed is not None:
        cmd += ["-s", str(seed)]
    cmd.append(state)

    logger.info(f"Running Synthea: population={n:,}, state={state}, output={out}")
    logger.debug(" ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        logger.error(f"Synthea exited with code {result.returncode}")
        sys.exit(result.returncode)

    # Synthea's CSV exporter writes into <baseDirectory>/csv/ by default;
    # synthea_loader.py expects the six CSVs directly inside synthea_output_dir.
    csv_dir = out / "csv"
    if csv_dir.exists():
        for csv_file in csv_dir.glob("*.csv"):
            csv_file.replace(out / csv_file.name)
        csv_dir.rmdir()

    logger.info(f"Synthea generation complete — CSVs written to {out}")


if __name__ == "__main__":
    main()
