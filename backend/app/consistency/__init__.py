"""Cross-Document Consistency Graph.

Each extracted field value becomes a node.
Edges connect values that should agree across documents.
Contradictions become evidence-linked findings.

Uses RapidFuzz for fuzzy name matching.
Numeric comparisons use configurable tolerance.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Any
from rapidfuzz import fuzz

# Tolerance for numeric comparisons (e.g. rounding in different docs)
NUMERIC_TOLERANCE_PCT = 5.0
NAME_SIMILARITY_THRESHOLD = 85.0  # RapidFuzz score 0-100


@dataclass
class ConsistencyNode:
    field_id: str
    field_key: str
    value: Any
    unit: Optional[str]
    doc_type: str
    document_id: str
    page_no: Optional[int]
    bbox: Optional[list]


@dataclass
class ConsistencyFinding:
    field_a_id: str
    field_b_id: str
    relation: str  # e.g. "land_area_cross_check"
    status: str    # CONSISTENT | MISMATCH | FUZZY_MATCH
    similarity: Optional[float]
    detail: dict
    severity: str


# ─── Consistency rules ────────────────────────────────────────────────────────

# Maps a "relation" to a pair of field_keys that should match
CONSISTENCY_CHECKS = [
    {
        "relation": "institution_name_consistency",
        "field_keys": ["institution_name"],
        "type": "name",
        "severity": "ADVISORY",
    },
    {
        "relation": "land_area_cross_check",
        "field_keys": ["total_land_area_acres", "deed_land_area_acres"],
        "type": "numeric",
        "severity": "MAJOR",
    },
    {
        "relation": "buildup_area_cross_check",
        "field_keys": ["total_buildup_area_sqm", "plan_buildup_area_sqm"],
        "type": "numeric",
        "severity": "MAJOR",
    },
    {
        "relation": "faculty_affidavit_list_check",
        "field_keys": ["affidavit_faculty_names", "faculty_list_names"],
        "type": "set",
        "severity": "MAJOR",
    },
]


def _numeric_similarity(a: float, b: float) -> tuple[str, float]:
    if b == 0:
        if a == 0:
            return "CONSISTENT", 100.0
        return "MISMATCH", 0.0
    diff_pct = abs(a - b) / abs(b) * 100
    similarity = max(0.0, 100.0 - diff_pct)
    if diff_pct <= NUMERIC_TOLERANCE_PCT:
        return "CONSISTENT", similarity
    return "MISMATCH", similarity


INSTITUTION_ABBREVIATIONS = {
    "inst": "institute",
    "tech": "technology",
    "engg": "engineering",
    "mgmt": "management",
    "coll": "college",
    "dept": "department",
    "univ": "university",
}


def _expand_abbreviations(text: str) -> str:
    tokens = text.split()
    return " ".join(INSTITUTION_ABBREVIATIONS.get(t.rstrip("."), t.rstrip(".")) for t in tokens)


def _name_similarity(a: str, b: str) -> tuple[str, float]:
    from app.pipeline.normalise import normalise_name
    a_norm = normalise_name(a)
    b_norm = normalise_name(b)
    score = fuzz.token_sort_ratio(a_norm, b_norm)
    if score >= NAME_SIMILARITY_THRESHOLD:
        return "FUZZY_MATCH" if score < 100 else "CONSISTENT", float(score)

    # Check with standard educational abbreviations expanded
    a_exp = _expand_abbreviations(a_norm)
    b_exp = _expand_abbreviations(b_norm)
    score_exp = fuzz.token_sort_ratio(a_exp, b_exp)
    if score_exp >= NAME_SIMILARITY_THRESHOLD:
        return "FUZZY_MATCH" if score_exp < 100 or a_norm != b_norm else "CONSISTENT", float(score_exp)

    return "MISMATCH", float(score)


def _set_difference(set_a: list[str], set_b: list[str]) -> tuple[str, float, dict]:
    """Check if names in set_a are all in set_b (fuzzy)."""
    from app.pipeline.normalise import normalise_name
    norm_a = [normalise_name(n) for n in set_a]
    norm_b = [normalise_name(n) for n in set_b]

    missing_from_b = []
    for name_a in norm_a:
        best = max((fuzz.token_sort_ratio(name_a, nb) for nb in norm_b), default=0)
        if best < NAME_SIMILARITY_THRESHOLD:
            missing_from_b.append(name_a)

    if not missing_from_b:
        return "CONSISTENT", 100.0, {}
    similarity = (len(norm_a) - len(missing_from_b)) / len(norm_a) * 100
    return "MISMATCH", similarity, {"missing_from_list": missing_from_b}


def run_consistency_checks(nodes: list[ConsistencyNode]) -> list[ConsistencyFinding]:
    """Run all consistency checks on a set of field nodes."""
    findings = []

    for check in CONSISTENCY_CHECKS:
        matching_nodes = [n for n in nodes if n.field_key in check["field_keys"]]
        if len(matching_nodes) < 2:
            continue  # Not enough data to compare

        # Compare pairwise
        for i in range(len(matching_nodes)):
            for j in range(i + 1, len(matching_nodes)):
                a = matching_nodes[i]
                b = matching_nodes[j]

                if a.value is None or b.value is None:
                    continue

                check_type = check["type"]
                relation = check["relation"]
                severity = check["severity"]

                if check_type == "numeric":
                    try:
                        av = float(a.value.value if hasattr(a.value, 'value') else a.value)
                        bv = float(b.value.value if hasattr(b.value, 'value') else b.value)
                        status, similarity = _numeric_similarity(av, bv)
                        detail = {
                            "a_value": av, "a_unit": a.unit, "a_doc": a.doc_type,
                            "b_value": bv, "b_unit": b.unit, "b_doc": b.doc_type,
                            "diff_pct": abs(av - bv) / bv * 100 if bv != 0 else None,
                        }
                    except (TypeError, ValueError):
                        continue

                elif check_type == "name":
                    av = str(a.value.value if hasattr(a.value, 'value') else a.value)
                    bv = str(b.value.value if hasattr(b.value, 'value') else b.value)
                    status, similarity = _name_similarity(av, bv)
                    detail = {"a_name": av, "b_name": bv, "a_doc": a.doc_type, "b_doc": b.doc_type}

                elif check_type == "set":
                    av = a.value if isinstance(a.value, list) else [str(a.value)]
                    bv = b.value if isinstance(b.value, list) else [str(b.value)]
                    status, similarity, extra = _set_difference(av, bv)
                    detail = {"a_doc": a.doc_type, "b_doc": b.doc_type, **extra}

                else:
                    continue

                findings.append(ConsistencyFinding(
                    field_a_id=a.field_id,
                    field_b_id=b.field_id,
                    relation=relation,
                    status=status,
                    similarity=similarity,
                    detail=detail,
                    severity=severity if status == "MISMATCH" else "ADVISORY",
                ))

    return findings
