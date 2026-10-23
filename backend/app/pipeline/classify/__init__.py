"""Document and page classifier using keyword and layout rules.

Stage 1: keyword matching (fast, interpretable).
Stage 2: TF-IDF + logistic regression (optional upgrade, requires labelled data).
Unknown documents go to officer queue.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional

from app.pipeline.ocr import WordToken

# ─── Classification rules ─────────────────────────────────────────────────────

# Map doc_type → keywords (case-insensitive, at least N must match)
DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "APPLICATION_FORM": [
        "application", "form", "aicte", "approval", "program",
        "intake", "institution", "academic year",
    ],
    "FACULTY_LIST": [
        "faculty", "staff", "qualification", "designation", "experience",
        "professor", "assistant professor", "associate professor",
    ],
    "FINANCIAL_STATEMENT": [
        "balance sheet", "income", "expenditure", "auditor", "chartered accountant",
        "profit", "loss", "annual report", "corpus",
    ],
    "LAND_DEED": [
        "sale deed", "deed", "registrar", "survey number", "land", "area",
        "transfer", "property", "registration", "vendor", "vendee",
    ],
    "BUILDING_PLAN": [
        "building plan", "floor plan", "elevation", "section", "architect",
        "scale", "ground floor", "first floor", "area statement",
    ],
    "FACULTY_AFFIDAVIT": [
        "affidavit", "notary", "deponent", "solemnly affirm",
        "faculty", "employed", "full time",
    ],
}

MIN_KEYWORD_MATCHES: dict[str, int] = {
    "APPLICATION_FORM": 3,
    "FACULTY_LIST": 3,
    "FINANCIAL_STATEMENT": 3,
    "LAND_DEED": 3,
    "BUILDING_PLAN": 3,
    "FACULTY_AFFIDAVIT": 3,
}


@dataclass
class ClassificationResult:
    doc_type: str  # or "UNKNOWN"
    confidence: float
    matched_keywords: list[str]


def classify_document(tokens: list[WordToken]) -> ClassificationResult:
    """Classify a document from its OCR tokens."""
    # Join all text into one string for matching
    full_text = " ".join(t.text for t in tokens).lower()
    return classify_text(full_text)


def classify_text(text: str) -> ClassificationResult:
    """Classify from a plain text string."""
    text_lower = text.lower()
    scores: dict[str, tuple[int, list[str]]] = {}

    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        matched = [kw for kw in keywords if kw in text_lower]
        scores[doc_type] = (len(matched), matched)

    if not scores:
        return ClassificationResult("UNKNOWN", 0.0, [])

    best_type = max(scores, key=lambda k: scores[k][0])
    best_count, best_matched = scores[best_type]
    required = MIN_KEYWORD_MATCHES.get(best_type, 3)

    if best_count < required:
        return ClassificationResult("UNKNOWN", best_count / required, best_matched)

    confidence = min(1.0, best_count / (required * 2))
    return ClassificationResult(best_type, confidence, best_matched)
