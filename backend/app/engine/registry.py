"""Registry of pure, deterministic rule evaluation functions.

Each function takes typed fact values (already normalised) and
returns one of: "PASS", "FAIL", "INDETERMINATE".

Functions never call LLMs, databases, or external services.
"""
from typing import Optional, Any


def _indeterminate_if_none(*values) -> Optional[str]:
    """Return INDETERMINATE if any value is None (missing/low-confidence input)."""
    if any(v is None for v in values):
        return "INDETERMINATE"
    return None


# ─── Core evaluation functions ────────────────────────────────────────────────

def ratio_at_least(
    numerator: Optional[float],
    denominator: Optional[float],
    minimum: float,
) -> tuple[str, str]:
    """Check numerator/denominator >= minimum."""
    ind = _indeterminate_if_none(numerator, denominator)
    if ind:
        return ind, "Required inputs are missing or low-confidence (INDETERMINATE)"
    if denominator == 0:
        return "INDETERMINATE", "Denominator is zero"
    ratio = numerator / denominator
    if round(ratio, 4) >= minimum:
        return "PASS", f"Ratio {ratio:.4f} >= required {minimum}"
    return "FAIL", f"Ratio {ratio:.4f} < required {minimum}"


def sum_at_least(
    total: Optional[float],
    minimum: float,
) -> tuple[str, str]:
    """Check total >= minimum."""
    ind = _indeterminate_if_none(total)
    if ind:
        return ind, "Required input is missing or low-confidence"
    if total >= minimum:
        return "PASS", f"Value {total} >= required {minimum}"
    return "FAIL", f"Value {total} < required {minimum}"


def area_at_least(
    area: Optional[float],
    minimum: float,
) -> tuple[str, str]:
    """Check area (in sq m) >= minimum (sq m)."""
    return sum_at_least(area, minimum)


def value_equals_within_tolerance(
    observed: Optional[float],
    expected: float,
    tolerance_pct: float = 5.0,
) -> tuple[str, str]:
    """Check |observed - expected| / expected <= tolerance_pct%."""
    ind = _indeterminate_if_none(observed)
    if ind:
        return ind, "Required input is missing"
    if expected == 0:
        if observed == 0:
            return "PASS", "Both values are zero"
        return "FAIL", f"Expected 0, found {observed}"
    diff_pct = abs(observed - expected) / abs(expected) * 100
    if diff_pct <= tolerance_pct:
        return "PASS", f"Difference {diff_pct:.2f}% within tolerance {tolerance_pct}%"
    return "FAIL", f"Difference {diff_pct:.2f}% exceeds tolerance {tolerance_pct}%"


def set_complete(
    present_items: Optional[list],
    required_items: list,
) -> tuple[str, str]:
    """Check that all required_items are present_items."""
    ind = _indeterminate_if_none(present_items)
    if ind:
        return ind, "Document list is missing or low-confidence"
    missing = [r for r in required_items if r not in present_items]
    if not missing:
        return "PASS", f"All {len(required_items)} required items present"
    return "FAIL", f"Missing items: {missing}"


def cadre_proportion_at_least(
    cadre_count: Optional[float],
    total_faculty: Optional[float],
    minimum_proportion: float,
) -> tuple[str, str]:
    """Check cadre_count/total_faculty >= minimum_proportion."""
    return ratio_at_least(cadre_count, total_faculty, minimum_proportion)


def value_in_range(
    value: Optional[float],
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
) -> tuple[str, str]:
    """Check value falls in [minimum, maximum] (either bound can be None = unbounded)."""
    ind = _indeterminate_if_none(value)
    if ind:
        return ind, "Required input is missing"
    if minimum is not None and value < minimum:
        return "FAIL", f"Value {value} < minimum {minimum}"
    if maximum is not None and value > maximum:
        return "FAIL", f"Value {value} > maximum {maximum}"
    return "PASS", f"Value {value} in range [{minimum}, {maximum}]"


# ─── Registry mapping ─────────────────────────────────────────────────────────

FUNCTION_REGISTRY: dict[str, callable] = {
    "ratio_at_least": ratio_at_least,
    "sum_at_least": sum_at_least,
    "area_at_least": area_at_least,
    "value_equals_within_tolerance": value_equals_within_tolerance,
    "set_complete": set_complete,
    "cadre_proportion_at_least": cadre_proportion_at_least,
    "value_in_range": value_in_range,
}
