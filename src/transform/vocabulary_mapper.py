"""Vocabulary mapping: translate source clinical codes to OMOP standard concepts.

Synthea uses a mix of coding systems — SNOMED CT for conditions, RxNorm for
medications, LOINC for observations, CPT/HCPCS for procedures. The OMOP CDM
requires all concepts to be mapped to "standard" vocabulary entries, which
means looking up each source code in the OHDSI vocabulary tables and finding
its standard concept_id.

This module loads the Athena vocabulary files (CONCEPT.csv,
CONCEPT_RELATIONSHIP.csv) and provides lookup functions that the transformer
uses during the OMOP conversion.

Key vocabulary tables from Athena:
  - CONCEPT: every concept in every vocabulary, with domain, class, and
    standard/non-standard flag
  - CONCEPT_RELATIONSHIP: mappings between concepts, including the critical
    "Maps to" relationship that connects source codes to standard concepts
"""

from pathlib import Path

import pandas as pd
from loguru import logger

from src.config.settings import settings


class VocabularyMapper:
    """Load OHDSI vocabularies and resolve source codes to standard concept IDs."""

    def __init__(self, vocab_dir: Path | None = None):
        self.vocab_dir = vocab_dir or settings.vocabulary_dir
        self._concept: pd.DataFrame | None = None
        self._concept_relationship: pd.DataFrame | None = None

    def load(self) -> None:
        """Load vocabulary files into memory. Called once at pipeline start."""
        logger.info(f"Loading vocabularies from {self.vocab_dir}")

        concept_path = self.vocab_dir / "CONCEPT.csv"
        relationship_path = self.vocab_dir / "CONCEPT_RELATIONSHIP.csv"

        if not concept_path.exists():
            raise FileNotFoundError(
                f"CONCEPT.csv not found at {concept_path}. "
                f"Download vocabularies from https://athena.ohdsi.org/"
            )

        # "None" is a real OMOP vocabulary_id (it's what concept_id=0 belongs
        # to), not a placeholder for a missing value — pandas' default NA
        # sentinel list would otherwise silently turn that literal text into
        # NaN on read. Only a genuinely empty field should parse as null here.
        self._concept = pd.read_csv(
            concept_path, sep="\t", low_memory=False,
            dtype={"concept_id": int, "concept_code": str},
            keep_default_na=False, na_values=[""],
        )
        logger.info(f"  CONCEPT: {len(self._concept):,} rows")

        self._concept_relationship = pd.read_csv(
            relationship_path, sep="\t", low_memory=False,
            dtype={"concept_id_1": int, "concept_id_2": int},
            keep_default_na=False, na_values=[""],
        )
        logger.info(f"  CONCEPT_RELATIONSHIP: {len(self._concept_relationship):,} rows")

        # Build the "Maps to" lookup: source concept_id -> standard concept_id
        maps_to = self._concept_relationship[
            self._concept_relationship["relationship_id"] == "Maps to"
        ]
        self._maps_to_lookup = dict(
            zip(maps_to["concept_id_1"], maps_to["concept_id_2"])
        )
        logger.info(f"  Maps-to lookup: {len(self._maps_to_lookup):,} mappings")

        # Build (vocabulary_id, concept_code) -> concept_id for O(1) source
        # lookups. source_to_concept_id used to run a full boolean-mask scan
        # of the concept table on every call — fine for a handful of calls,
        # but this pipeline resolves one of these per row of every clinical
        # table, which is several hundred thousand calls on even a modest
        # demo population (measured: 68,943 rows took 35 seconds against a
        # 73-row concept table, because the cost was pandas' own per-call
        # overhead, not the table size). A dict built once here turns each of
        # those from a DataFrame filter into a hash lookup.
        self._code_lookup: dict[tuple[str, str], int] = {
            (vocabulary_id, str(code)): int(concept_id)
            for vocabulary_id, code, concept_id in zip(
                self._concept["vocabulary_id"],
                self._concept["concept_code"],
                self._concept["concept_id"],
            )
        }

    @property
    def concept(self) -> pd.DataFrame:
        if self._concept is None:
            raise RuntimeError("Vocabularies not loaded. Call .load() first.")
        return self._concept

    def source_to_concept_id(self, code: str, vocabulary_id: str) -> int | None:
        """Look up a source code in a given vocabulary and return its concept_id.

        Args:
            code: The source code (e.g., "44054006" for SNOMED diabetes)
            vocabulary_id: The vocabulary (e.g., "SNOMED", "RxNorm", "LOINC")

        Returns:
            concept_id if found, None otherwise
        """
        if self._concept is None:
            raise RuntimeError("Vocabularies not loaded. Call .load() first.")
        return self._code_lookup.get((vocabulary_id, str(code)))

    def to_standard(self, concept_id: int) -> int:
        """Follow the 'Maps to' relationship to get the standard concept_id.

        If no mapping exists, returns the input concept_id (it may already be
        standard, or it may be unmapped — the caller decides how to handle that).
        """
        return self._maps_to_lookup.get(concept_id, concept_id)

    def resolve(self, code: str, vocabulary_id: str) -> tuple[int, int]:
        """Full resolution: source code -> source concept_id -> standard concept_id.

        Returns:
            (source_concept_id, standard_concept_id). Either may be 0 if
            the code is not found in the vocabulary.
        """
        source_id = self.source_to_concept_id(code, vocabulary_id)
        if source_id is None:
            return (0, 0)
        standard_id = self.to_standard(source_id)
        return (source_id, standard_id)

    def mapping_coverage(self, codes: list[str], vocabulary_id: str) -> dict:
        """Calculate what fraction of source codes successfully map to standard
        concepts. Used for data quality reporting."""
        total = len(codes)
        mapped = sum(1 for c in codes if self.resolve(c, vocabulary_id)[1] != 0)
        return {
            "total_codes": total,
            "mapped_codes": mapped,
            "unmapped_codes": total - mapped,
            "coverage_pct": round(mapped / total * 100, 2) if total else 0.0,
        }
