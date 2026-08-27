"""Tests for the vocabulary mapper module.

These tests use a small in-memory vocabulary fixture rather than the full
Athena download, so they run without any external dependencies.
"""

import pandas as pd
import pytest

from src.transform.vocabulary_mapper import VocabularyMapper


@pytest.fixture
def mapper_with_fixtures(tmp_path):
    """Create a VocabularyMapper loaded with a small test vocabulary."""
    # Minimal CONCEPT.csv
    concept_data = pd.DataFrame({
        "concept_id": [44054006, 8507, 8532, 1000, 2000],
        "concept_name": [
            "Type 2 diabetes mellitus",
            "Male", "Female",
            "Metformin", "Diabetes Mellitus",
        ],
        "domain_id": ["Condition", "Gender", "Gender", "Drug", "Condition"],
        "vocabulary_id": ["SNOMED", "Gender", "Gender", "RxNorm", "SNOMED"],
        "concept_class_id": ["Clinical Finding", "Gender", "Gender", "Ingredient", "Clinical Finding"],
        "standard_concept": ["S", "S", "S", "S", "S"],
        "concept_code": ["44054006", "M", "F", "6809", "73211009"],
    })

    # Minimal CONCEPT_RELATIONSHIP.csv
    relationship_data = pd.DataFrame({
        "concept_id_1": [44054006, 1000],
        "concept_id_2": [2000, 1000],
        "relationship_id": ["Maps to", "Maps to"],
    })

    concept_data.to_csv(tmp_path / "CONCEPT.csv", sep="\t", index=False)
    relationship_data.to_csv(tmp_path / "CONCEPT_RELATIONSHIP.csv", sep="\t", index=False)

    mapper = VocabularyMapper(vocab_dir=tmp_path)
    mapper.load()
    return mapper


class TestVocabularyMapper:
    def test_source_to_concept_id_found(self, mapper_with_fixtures):
        result = mapper_with_fixtures.source_to_concept_id("44054006", "SNOMED")
        assert result == 44054006

    def test_source_to_concept_id_not_found(self, mapper_with_fixtures):
        result = mapper_with_fixtures.source_to_concept_id("99999999", "SNOMED")
        assert result is None

    def test_source_to_concept_id_wrong_vocabulary(self, mapper_with_fixtures):
        result = mapper_with_fixtures.source_to_concept_id("44054006", "RxNorm")
        assert result is None

    def test_to_standard_with_mapping(self, mapper_with_fixtures):
        # 44054006 maps to 2000
        result = mapper_with_fixtures.to_standard(44054006)
        assert result == 2000

    def test_to_standard_without_mapping(self, mapper_with_fixtures):
        # 8507 has no Maps-to relationship, so it returns itself
        result = mapper_with_fixtures.to_standard(8507)
        assert result == 8507

    def test_resolve_full_chain(self, mapper_with_fixtures):
        source_id, standard_id = mapper_with_fixtures.resolve("44054006", "SNOMED")
        assert source_id == 44054006
        assert standard_id == 2000

    def test_resolve_not_found(self, mapper_with_fixtures):
        source_id, standard_id = mapper_with_fixtures.resolve("UNKNOWN", "SNOMED")
        assert source_id == 0
        assert standard_id == 0

    def test_mapping_coverage(self, mapper_with_fixtures):
        codes = ["44054006", "73211009", "UNKNOWN_CODE"]
        result = mapper_with_fixtures.mapping_coverage(codes, "SNOMED")
        assert result["total_codes"] == 3
        assert result["mapped_codes"] == 2
        assert result["unmapped_codes"] == 1
        assert result["coverage_pct"] == pytest.approx(66.67, abs=0.01)

    def test_mapping_coverage_empty(self, mapper_with_fixtures):
        result = mapper_with_fixtures.mapping_coverage([], "SNOMED")
        assert result["coverage_pct"] == 0.0
