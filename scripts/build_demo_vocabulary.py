"""Build a demo-scale OHDSI vocabulary from the catalog in scripts/demo_codes.py.

The real OHDSI Athena vocabulary is a multi-gigabyte export that requires a
licensed account at athena.ohdsi.org to obtain — see
scripts/download_vocabularies.py for that path. This script exists so the
pipeline has something to actually run against without one: it writes the same
file names, the same tab-separated format, and the same column layout Athena
exports use, populated from roughly forty hand-picked SNOMED, RxNorm, and LOINC
codes rather than the full standard vocabulary.

Run it before scripts/generate_demo_data.py — the demo data generator only
emits codes this vocabulary knows about (plus a deliberate handful it doesn't,
so mapping-coverage numbers mean something).
"""

from datetime import date
from pathlib import Path

import click
import pandas as pd
from loguru import logger

from scripts.demo_codes import (
    ALL_NONSTANDARD_CODES,
    ALL_STANDARD_CODES,
    ETHNICITY_CONCEPTS,
    GENDER_CONCEPTS,
    NO_MATCHING_CONCEPT,
    RACE_CONCEPTS,
    TYPE_CONCEPTS,
    VISIT_CONCEPTS,
)
from src.config.settings import settings

VALID_START = date(1970, 1, 1)
VALID_END = date(2099, 12, 31)

DOMAINS = [
    ("Condition", "Condition"), ("Drug", "Drug"), ("Measurement", "Measurement"),
    ("Observation", "Observation"), ("Procedure", "Procedure"), ("Gender", "Gender"),
    ("Race", "Race"), ("Ethnicity", "Ethnicity"), ("Visit", "Visit"),
    ("Type Concept", "Type Concept"), ("Metadata", "Metadata"),
]

VOCABULARIES = [
    ("SNOMED", "Systematic Nomenclature of Medicine - Clinical Terms"),
    ("RxNorm", "RxNorm"),
    ("LOINC", "Logical Observation Identifiers Names and Codes"),
    ("Gender", "OMOP Gender"),
    ("Race", "Race and Ethnicity Code Set (USBC)"),
    ("Ethnicity", "OMOP Ethnicity"),
    ("Visit", "OMOP Visit"),
    ("Type Concept", "OMOP Type Concept"),
    ("None", "OMOP Standard vocabulary"),
]

CONCEPT_CLASSES = [
    "Clinical Finding", "Ingredient", "Clinical Drug", "Lab Test",
    "Clinical Observation", "Procedure", "Gender", "Race", "Ethnicity",
    "Visit", "Type Concept", "Undefined",
]

RELATIONSHIPS = [
    ("Maps to", "Maps to", "0", "0", "Mapped from"),
    ("Mapped from", "Mapped from", "0", "0", "Maps to"),
]


def build_domain() -> pd.DataFrame:
    return pd.DataFrame([
        {"domain_id": d, "domain_name": name, "domain_concept_id": 0}
        for d, name in DOMAINS
    ])


def build_vocabulary() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "vocabulary_id": v, "vocabulary_name": name,
            "vocabulary_reference": "https://athena.ohdsi.org/",
            "vocabulary_version": "demo-seed", "vocabulary_concept_id": 0,
        }
        for v, name in VOCABULARIES
    ])


def build_concept_class() -> pd.DataFrame:
    return pd.DataFrame([
        {"concept_class_id": c, "concept_class_name": c, "concept_class_concept_id": 0}
        for c in CONCEPT_CLASSES
    ])


def build_relationship() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "relationship_id": r, "relationship_name": name,
            "is_hierarchical": h, "defines_ancestry": a,
            "reverse_relationship_id": rev, "relationship_concept_id": 0,
        }
        for r, name, h, a, rev in RELATIONSHIPS
    ])


def build_concept() -> pd.DataFrame:
    rows = [{
        "concept_id": NO_MATCHING_CONCEPT[0],
        "concept_name": NO_MATCHING_CONCEPT[1],
        "domain_id": "Metadata",
        "vocabulary_id": "None",
        "concept_class_id": "Undefined",
        "standard_concept": None,
        "concept_code": "OMOP generated",
        "valid_start_date": VALID_START,
        "valid_end_date": VALID_END,
        "invalid_reason": None,
    }]

    for concept_id, name, domain_id, vocabulary_id, concept_class_id in (
        [(cid, name, "Gender", "Gender", "Gender") for cid, name in GENDER_CONCEPTS]
        + [(cid, name, "Race", "Race", "Race") for cid, name in RACE_CONCEPTS]
        + [(cid, name, "Ethnicity", "Ethnicity", "Ethnicity") for cid, name in ETHNICITY_CONCEPTS]
        + [(cid, name, "Visit", "Visit", "Visit") for cid, name in VISIT_CONCEPTS]
        + [(cid, name, "Type Concept", "Type Concept", "Type Concept") for cid, name in TYPE_CONCEPTS]
    ):
        rows.append({
            "concept_id": concept_id, "concept_name": name, "domain_id": domain_id,
            "vocabulary_id": vocabulary_id, "concept_class_id": concept_class_id,
            "standard_concept": "S", "concept_code": name.upper().replace(" ", "_"),
            "valid_start_date": VALID_START, "valid_end_date": VALID_END, "invalid_reason": None,
        })

    for c in ALL_STANDARD_CODES + ALL_NONSTANDARD_CODES:
        rows.append({
            "concept_id": c.concept_id, "concept_name": c.concept_name, "domain_id": c.domain_id,
            "vocabulary_id": c.vocabulary_id, "concept_class_id": c.concept_class_id,
            "standard_concept": "S" if c.standard else None, "concept_code": c.code,
            "valid_start_date": VALID_START, "valid_end_date": VALID_END, "invalid_reason": None,
        })

    return pd.DataFrame(rows)


def build_concept_relationship() -> pd.DataFrame:
    rows = []
    for c in ALL_NONSTANDARD_CODES:
        rows.append({
            "concept_id_1": c.concept_id, "concept_id_2": c.maps_to.concept_id,
            "relationship_id": "Maps to", "valid_start_date": VALID_START,
            "valid_end_date": VALID_END, "invalid_reason": None,
        })
        rows.append({
            "concept_id_1": c.maps_to.concept_id, "concept_id_2": c.concept_id,
            "relationship_id": "Mapped from", "valid_start_date": VALID_START,
            "valid_end_date": VALID_END, "invalid_reason": None,
        })
    return pd.DataFrame(rows)


TABLE_BUILDERS = {
    "DOMAIN.csv": build_domain,
    "VOCABULARY.csv": build_vocabulary,
    "CONCEPT_CLASS.csv": build_concept_class,
    "RELATIONSHIP.csv": build_relationship,
    "CONCEPT.csv": build_concept,
    "CONCEPT_RELATIONSHIP.csv": build_concept_relationship,
}


@click.command()
@click.option(
    "--output-dir", type=click.Path(path_type=Path), default=None,
    help="Where to write the vocabulary files. Defaults to settings.vocabulary_dir.",
)
def main(output_dir: Path | None):
    """Write a demo-scale OHDSI vocabulary to disk in Athena's own file format."""
    out = output_dir or settings.vocabulary_dir
    out.mkdir(parents=True, exist_ok=True)

    logger.info(f"Building demo vocabulary in {out}")
    for filename, builder in TABLE_BUILDERS.items():
        df = builder()
        df.to_csv(out / filename, sep="\t", index=False)
        logger.info(f"  {filename}: {len(df):,} rows")

    logger.info("Demo vocabulary ready. This is a hand-picked subset for local "
                "development — swap in a real Athena export for production use.")


if __name__ == "__main__":
    main()
