"""Organize a real OHDSI Athena vocabulary download for the pipeline to use.

Athena vocabularies aren't available through any API — getting them means an
account at athena.ohdsi.org, accepting the license agreement for whatever
vocabularies you select (SNOMED CT, RxNorm, and LOINC, at minimum, for this
pipeline), and downloading the zip Athena emails a link to once it's built.
This script picks up from there: given that zip, it extracts it, checks which
of the standard vocabulary files actually arrived, and stages them in
settings.vocabulary_dir, where src/transform/vocabulary_mapper.py and
src/load/warehouse_loader.py both expect to find them.

scripts/build_demo_vocabulary.py fills the same directory with a much smaller
hand-picked seed for local development, where a licensed download usually
isn't available. This script is what replaces that seed with the real thing.
"""

import shutil
import zipfile
from pathlib import Path

import click
from loguru import logger

from src.config.settings import settings

EXPECTED_FILES = [
    "CONCEPT.csv", "CONCEPT_RELATIONSHIP.csv", "VOCABULARY.csv", "DOMAIN.csv",
    "CONCEPT_CLASS.csv", "RELATIONSHIP.csv", "CONCEPT_SYNONYM.csv",
    "CONCEPT_ANCESTOR.csv", "DRUG_STRENGTH.csv",
]


@click.command()
@click.argument("zip_path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output-dir", type=click.Path(path_type=Path), default=None,
    help="Defaults to settings.vocabulary_dir.",
)
@click.option("--overwrite", is_flag=True, help="Replace any existing vocabulary files without asking.")
def main(zip_path: Path, output_dir: Path | None, overwrite: bool):
    """Extract an Athena vocabulary download and stage it for the pipeline.

    ZIP_PATH is the file Athena gives you a download link for, after
    selecting vocabularies and accepting their license terms at
    https://athena.ohdsi.org/.
    """
    out = output_dir or settings.vocabulary_dir
    out.mkdir(parents=True, exist_ok=True)

    existing = [f for f in EXPECTED_FILES if (out / f).exists()]
    if existing and not overwrite:
        logger.warning(
            f"{len(existing)} vocabulary files already exist in {out} (for example, "
            f"from scripts/build_demo_vocabulary.py). Pass --overwrite to replace them."
        )
        return

    logger.info(f"Extracting {zip_path} to {out}")
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out)

    # Athena's zip sometimes nests the CSVs one directory down; flatten if so.
    for nested in out.rglob("*.csv"):
        if nested.parent != out:
            shutil.move(str(nested), out / nested.name)

    found = [f for f in EXPECTED_FILES if (out / f).exists()]
    missing = [f for f in EXPECTED_FILES if f not in found]

    logger.info(f"Vocabulary files ready in {out}: {len(found)}/{len(EXPECTED_FILES)} expected files present")
    for f in found:
        size_mb = (out / f).stat().st_size / 1e6
        logger.info(f"  {f}: {size_mb:.1f} MB")
    if missing:
        logger.warning(f"Missing from this download: {missing}")


if __name__ == "__main__":
    main()
