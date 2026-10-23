"""Unit tests for the rule engine.

Tests each rule function:
- exactly at threshold
- just below threshold
- missing input (INDETERMINATE)
- well above threshold

No database, no filesystem, no LLM. Pure function calls.
"""
import pytest
from app.engine.registry import (
    ratio_at_least, sum_at_least, area_at_least,
    value_equals_within_tolerance, set_complete, cadre_proportion_at_least,
)
from app.engine.evaluator import evaluate_rule, run_rule_tests, FactValue
from app.engine.loader import load_rulebook_from_dir
from pathlib import Path


class TestRatioAtLeast:
    def test_above_threshold(self):
        status, msg = ratio_at_least(100.0, 1200.0, 0.0667)
        assert status == "PASS"

    def test_exactly_at_threshold(self):
        # 80/1200 = 0.0667 (to 4 decimal places: 0.0667)
        status, msg = ratio_at_least(80.04, 1200.0, 0.0667)
        assert status == "PASS"

    def test_just_below_threshold(self):
        # 79/1200 = 0.06583...
        status, msg = ratio_at_least(79.0, 1200.0, 0.0667)
        assert status == "FAIL"

    def test_missing_numerator(self):
        status, msg = ratio_at_least(None, 1200.0, 0.0667)
        assert status == "INDETERMINATE"

    def test_missing_denominator(self):
        status, msg = ratio_at_least(100.0, None, 0.0667)
        assert status == "INDETERMINATE"

    def test_zero_denominator(self):
        status, msg = ratio_at_least(100.0, 0.0, 0.0667)
        assert status == "INDETERMINATE"

    def test_demo_scenario_fail(self):
        """Demo scenario: 58 faculty / 1200 intake = 0.0483 < 0.0667"""
        status, msg = ratio_at_least(58.0, 1200.0, 0.0667)
        assert status == "FAIL"


class TestSumAtLeast:
    def test_pass(self):
        status, _ = sum_at_least(3.0, 2.5)
        assert status == "PASS"

    def test_fail(self):
        status, _ = sum_at_least(2.1, 2.5)
        assert status == "FAIL"

    def test_exactly_at_threshold(self):
        status, _ = sum_at_least(2.5, 2.5)
        assert status == "PASS"

    def test_missing(self):
        status, _ = sum_at_least(None, 2.5)
        assert status == "INDETERMINATE"


class TestValueEqualsWithinTolerance:
    def test_within_tolerance(self):
        status, _ = value_equals_within_tolerance(102.0, 100.0, tolerance_pct=5.0)
        assert status == "PASS"

    def test_outside_tolerance(self):
        status, _ = value_equals_within_tolerance(110.0, 100.0, tolerance_pct=5.0)
        assert status == "FAIL"

    def test_missing(self):
        status, _ = value_equals_within_tolerance(None, 100.0)
        assert status == "INDETERMINATE"


class TestSetComplete:
    def test_all_present(self):
        status, _ = set_complete(
            ["APPLICATION_FORM", "FACULTY_LIST", "FINANCIAL_STATEMENT",
             "LAND_DEED", "BUILDING_PLAN", "FACULTY_AFFIDAVIT"],
            ["APPLICATION_FORM", "FACULTY_LIST", "FINANCIAL_STATEMENT",
             "LAND_DEED", "BUILDING_PLAN", "FACULTY_AFFIDAVIT"],
        )
        assert status == "PASS"

    def test_missing_items(self):
        status, _ = set_complete(
            ["APPLICATION_FORM", "FACULTY_LIST"],
            ["APPLICATION_FORM", "FACULTY_LIST", "FINANCIAL_STATEMENT",
             "LAND_DEED", "BUILDING_PLAN", "FACULTY_AFFIDAVIT"],
        )
        assert status == "FAIL"

    def test_empty_list(self):
        status, _ = set_complete([], ["APPLICATION_FORM"])
        assert status == "FAIL"

    def test_missing_input(self):
        status, _ = set_complete(None, ["APPLICATION_FORM"])
        assert status == "INDETERMINATE"


class TestCadreProportion:
    def test_sufficient_professors(self):
        status, _ = cadre_proportion_at_least(15.0, 100.0, 0.10)
        assert status == "PASS"

    def test_insufficient_professors(self):
        status, _ = cadre_proportion_at_least(5.0, 100.0, 0.10)
        assert status == "FAIL"

    def test_missing(self):
        status, _ = cadre_proportion_at_least(None, 100.0, 0.10)
        assert status == "INDETERMINATE"


class TestEvaluateRule:
    def setup_method(self):
        self.fac_ratio_rule = {
            "rule_key": "FAC_RATIO_TEST",
            "title": "Test Faculty Ratio",
            "severity": "CRITICAL",
            "inputs": {
                "total_faculty": {"type": "int", "min_confidence": 0.85},
                "sanctioned_intake_total": {"type": "int", "min_confidence": 0.85},
            },
            "check": {
                "fn": "ratio_at_least",
                "params": {
                    "numerator": "total_faculty",
                    "denominator": "sanctioned_intake_total",
                    "minimum": 0.0667,
                },
            },
        }

    def test_pass(self):
        facts = {
            "total_faculty": FactValue(100, 0.95),
            "sanctioned_intake_total": FactValue(1200, 0.95),
        }
        result = evaluate_rule(self.fac_ratio_rule, facts)
        assert result.status == "PASS"

    def test_fail(self):
        facts = {
            "total_faculty": FactValue(50, 0.95),
            "sanctioned_intake_total": FactValue(1200, 0.95),
        }
        result = evaluate_rule(self.fac_ratio_rule, facts)
        assert result.status == "FAIL"

    def test_indeterminate_missing(self):
        facts = {
            "sanctioned_intake_total": FactValue(1200, 0.95),
        }
        result = evaluate_rule(self.fac_ratio_rule, facts)
        assert result.status == "INDETERMINATE"

    def test_indeterminate_low_confidence(self):
        facts = {
            "total_faculty": FactValue(100, 0.50),  # below 0.85 min_confidence
            "sanctioned_intake_total": FactValue(1200, 0.95),
        }
        result = evaluate_rule(self.fac_ratio_rule, facts)
        assert result.status == "INDETERMINATE"


class TestBuiltInRuleTests:
    """Run the YAML-embedded test cases from each rule file."""
    def test_rulebook_built_in_tests(self):
        rules_dir = Path(__file__).parent.parent.parent / "rulebooks" / "2026-27"
        if not rules_dir.exists():
            pytest.skip("Rulebook directory not found")

        try:
            rules, _ = load_rulebook_from_dir(rules_dir)
        except Exception as e:
            pytest.fail(f"Failed to load rulebook: {e}")

        all_failed = []
        for rule in rules:
            results = run_rule_tests(rule)
            failed = [r for r in results if not r["passed"]]
            if failed:
                all_failed.append({"rule_key": rule["rule_key"], "failures": failed})

        assert not all_failed, f"Rule test failures: {all_failed}"
