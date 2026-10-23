"""Rule engine evaluator.

Evaluates a set of rules (dicts from YAML) against a facts dict.
Facts are typed values with confidence scores.
Returns a list of FindingResult objects.

No LLM calls here. Deterministic only.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional
from app.engine.registry import FUNCTION_REGISTRY
from app.config import get_settings

settings = get_settings()

ENGINE_VERSION = "1.0.0"


@dataclass
class FactValue:
    value: Any  # the normalised value; None means INDETERMINATE
    confidence: float = 1.0  # 0.0 – 1.0
    field_id: Optional[str] = None
    page_id: Optional[str] = None
    bbox: Optional[list] = None
    unit: Optional[str] = None


@dataclass
class FindingResult:
    rule_key: str
    rule_id: Optional[str]  # DB id if known
    status: str  # PASS | FAIL | INDETERMINATE | NOT_APPLICABLE
    severity: str
    required_value: Optional[str]
    observed_value: Optional[str]
    explanation: str
    confidence: float
    evidence_field_ids: list[str] = field(default_factory=list)
    clause_ref: Optional[str] = None
    title: Optional[str] = None


def _resolve_facts(rule_def: dict, facts: dict[str, FactValue]) -> tuple[dict[str, Any], float, list[str]]:
    """
    Map input names from the rule spec to actual values.
    Returns (resolved_values, min_confidence, missing_fields).
    """
    inputs_spec = rule_def.get("inputs", {})
    resolved = {}
    min_conf = 1.0
    missing = []
    field_ids = []

    for input_name, spec in inputs_spec.items():
        fact = facts.get(input_name)
        min_confidence_required = spec.get("min_confidence", settings.OCR_FAST_FAIL_THRESHOLD)

        if fact is None or fact.value is None:
            resolved[input_name] = None
            missing.append(input_name)
        elif fact.confidence < min_confidence_required:
            # Below required confidence → treat as INDETERMINATE
            resolved[input_name] = None
            missing.append(input_name)
            min_conf = min(min_conf, fact.confidence)
        else:
            resolved[input_name] = fact.value
            min_conf = min(min_conf, fact.confidence)
            if fact.field_id:
                field_ids.append(fact.field_id)

    return resolved, min_conf, missing, field_ids


def evaluate_rule(rule_def: dict, facts: dict[str, FactValue], rule_db_id: Optional[str] = None) -> FindingResult:
    """Evaluate one rule against facts. Returns a FindingResult."""
    rule_key = rule_def["rule_key"]
    severity = rule_def["severity"]
    check = rule_def.get("check", {})
    fn_name = check.get("fn")
    params = check.get("params", {})
    explain_template = rule_def.get("explain", "")
    clause_ref = rule_def.get("clause_ref", "")
    title = rule_def.get("title", rule_key)

    # Check applicability (skip if not applicable)
    # (simplified: applicability filtering is done before calling this)

    # Resolve facts
    resolved, min_conf, missing, field_ids = _resolve_facts(rule_def, facts)

    if missing:
        return FindingResult(
            rule_key=rule_key,
            rule_id=rule_db_id,
            status="INDETERMINATE",
            severity=severity,
            required_value=None,
            observed_value=None,
            explanation=f"Missing or low-confidence inputs: {missing}",
            confidence=min_conf,
            evidence_field_ids=field_ids,
            clause_ref=clause_ref,
            title=title,
        )

    # Look up evaluation function
    if fn_name not in FUNCTION_REGISTRY:
        return FindingResult(
            rule_key=rule_key,
            rule_id=rule_db_id,
            status="INDETERMINATE",
            severity=severity,
            required_value=None,
            observed_value=None,
            explanation=f"Unknown evaluation function: {fn_name}",
            confidence=0.0,
            clause_ref=clause_ref,
            title=title,
        )

    fn = FUNCTION_REGISTRY[fn_name]

    # Build kwargs: map param values from resolved facts or literal values
    kwargs = {}
    for param_name, param_value in params.items():
        if isinstance(param_value, str) and param_value in resolved:
            kwargs[param_name] = resolved[param_value]
        else:
            kwargs[param_name] = param_value

    try:
        result_status, explanation = fn(**kwargs)
    except Exception as e:
        result_status = "INDETERMINATE"
        explanation = f"Evaluation error: {e}"

    # Format observed value for reporting
    observed_str = None
    required_str = None
    if fn_name == "ratio_at_least":
        num = kwargs.get("numerator")
        den = kwargs.get("denominator")
        minimum = kwargs.get("minimum")
        if num is not None and den is not None and den != 0:
            observed_str = f"{num}/{den} = {num/den:.4f}"
        required_str = str(minimum)
    elif fn_name in ("sum_at_least", "area_at_least"):
        observed_str = str(kwargs.get("total") or kwargs.get("area"))
        required_str = str(kwargs.get("minimum"))
    elif fn_name == "set_complete":
        observed_str = str(kwargs.get("present_items"))
        required_str = str(kwargs.get("required_items"))

    return FindingResult(
        rule_key=rule_key,
        rule_id=rule_db_id,
        status=result_status,
        severity=severity,
        required_value=required_str,
        observed_value=observed_str,
        explanation=explanation,
        confidence=min_conf,
        evidence_field_ids=field_ids,
        clause_ref=clause_ref,
        title=title,
    )


def evaluate_all_rules(
    rules: list[dict],
    facts: dict[str, FactValue],
    rule_db_ids: Optional[dict[str, str]] = None,
) -> list[FindingResult]:
    """Evaluate all rules and return findings list."""
    rule_db_ids = rule_db_ids or {}
    return [
        evaluate_rule(rule, facts, rule_db_id=rule_db_ids.get(rule["rule_key"]))
        for rule in rules
    ]


def run_rule_tests(rule_def: dict) -> list[dict]:
    """Run the built-in test cases from a rule definition. Returns test results."""
    tests = rule_def.get("tests", [])
    results = []
    for i, test in enumerate(tests):
        test_facts = {
            k: FactValue(value=v, confidence=1.0 if v is not None else 0.0)
            for k, v in test["inputs"].items()
        }
        finding = evaluate_rule(rule_def, test_facts)
        expected = test["expect"]
        passed = finding.status == expected
        results.append({
            "test_index": i,
            "inputs": test["inputs"],
            "expected": expected,
            "got": finding.status,
            "passed": passed,
            "explanation": finding.explanation,
        })
    return results
