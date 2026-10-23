"""Unit tests for consistency graph checks."""
import pytest
from app.consistency import (
    ConsistencyNode, run_consistency_checks,
    _numeric_similarity, _name_similarity,
)


class TestNumericSimilarity:
    def test_identical_values(self):
        status, sim = _numeric_similarity(3.0, 3.0)
        assert status == "CONSISTENT"
        assert sim == 100.0

    def test_within_tolerance(self):
        status, sim = _numeric_similarity(3.05, 3.0)
        assert status == "CONSISTENT"

    def test_outside_tolerance(self):
        # 2.10 vs 3.00 → 30% difference
        status, sim = _numeric_similarity(2.10, 3.00)
        assert status == "MISMATCH"

    def test_demo_land_mismatch(self):
        """Demo scenario: deed=2.10 acres vs application=3.00 acres"""
        status, sim = _numeric_similarity(2.10, 3.00)
        assert status == "MISMATCH"
        assert sim < 80.0


class TestNameSimilarity:
    def test_exact_match(self):
        status, score = _name_similarity("Sunrise Institute of Technology", "Sunrise Institute of Technology")
        assert status in ("CONSISTENT", "FUZZY_MATCH")
        assert score > 90

    def test_abbreviation_fuzzy(self):
        """Demo scenario: 'Sunrise Inst. of Tech.' vs 'Sunrise Institute of Technology'"""
        status, score = _name_similarity("Sunrise Inst. of Tech.", "Sunrise Institute of Technology")
        # Should be FUZZY_MATCH not MISMATCH
        assert status in ("FUZZY_MATCH", "CONSISTENT")

    def test_completely_different(self):
        status, score = _name_similarity("Alpha College", "Sunrise Institute of Technology")
        assert status == "MISMATCH"


class TestConsistencyGraph:
    def _make_node(self, field_key, value, field_id, doc_type):
        class FakeNorm:
            def __init__(self, v):
                self.value = v
        return ConsistencyNode(
            field_id=field_id,
            field_key=field_key,
            value=FakeNorm(value),
            unit="acres" if "area" in field_key else None,
            doc_type=doc_type,
            document_id=f"doc-{doc_type}",
            page_no=1,
            bbox=None,
        )

    def test_land_area_mismatch_detected(self):
        """Planted issue 2: deed=2.10 acres, application=3.00 acres → MISMATCH"""
        nodes = [
            self._make_node("total_land_area_acres", 3.00, "f1", "APPLICATION_FORM"),
            self._make_node("deed_land_area_acres", 2.10, "f2", "LAND_DEED"),
        ]
        findings = run_consistency_checks(nodes)
        mismatches = [f for f in findings if f.status == "MISMATCH"]
        assert len(mismatches) >= 1

    def test_land_area_consistent(self):
        nodes = [
            self._make_node("total_land_area_acres", 3.00, "f1", "APPLICATION_FORM"),
            self._make_node("deed_land_area_acres", 3.00, "f2", "LAND_DEED"),
        ]
        findings = run_consistency_checks(nodes)
        mismatches = [f for f in findings if f.status == "MISMATCH"]
        assert len(mismatches) == 0
