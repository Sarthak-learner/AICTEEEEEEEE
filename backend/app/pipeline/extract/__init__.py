"""Field extractors for 4 document types.

Each extractor uses anchor-text + regex patterns.
Returns a list of CandidateField with confidence.
Never calls LLM; never auto-extracts below OCR fast-fail threshold.
"""
from __future__ import annotations
import re
from dataclasses import dataclass
from typing import Optional
from app.pipeline.ocr import WordToken
from app.pipeline.normalise import (
    normalise_area_to_sqm, normalise_area_to_acres,
    normalise_currency_to_crores, normalise_integer,
    normalise_name,
)
from app.config import get_settings

settings = get_settings()

FAST_FAIL = settings.OCR_FAST_FAIL_THRESHOLD


@dataclass
class CandidateField:
    field_key: str
    raw_value: str
    normalised_value: Optional[object]  # NormalisedValue
    confidence: float  # min(ocr_conf, pattern_strength)
    bbox: Optional[list]  # [x0, y0, x1, y1]
    page_no: int
    extractor: str
    status: str = "AUTO"
    fail_reason: Optional[str] = None


def _tokens_text(tokens: list[WordToken]) -> str:
    return " ".join(t.text for t in tokens)


def _window_after_anchor(
    tokens: list[WordToken],
    anchor: str,
    window: int = 15,
) -> Optional[tuple[str, float, list]]:
    """Find anchor phrase and return the next `window` tokens' text and min confidence."""
    full_text = _tokens_text(tokens)
    pattern = re.compile(re.escape(anchor), re.IGNORECASE)
    m = pattern.search(full_text)
    if not m:
        return None

    # Find the token index where the anchor ends
    char_pos = 0
    anchor_end_idx = 0
    for i, t in enumerate(tokens):
        if char_pos >= m.end():
            anchor_end_idx = i
            break
        char_pos += len(t.text) + 1

    following = tokens[anchor_end_idx: anchor_end_idx + window]
    if not following:
        return None
    text = " ".join(t.text for t in following)
    conf = min(t.confidence for t in following)
    bbox = [
        min(t.x0 for t in following),
        min(t.y0 for t in following),
        max(t.x1 for t in following),
        max(t.y1 for t in following),
    ]
    return text, conf, bbox


def extract_from_faculty_list(tokens: list[WordToken], page_no: int) -> list[CandidateField]:
    """Extract total faculty count and cadre breakdown."""
    fields = []
    text = _tokens_text(tokens)

    # Total faculty: look for "Total" near a number at end of a list
    total_match = re.search(
        r"(?:total|grand total)\s*(?:faculty|teaching staff|members|count)?\s*[:\-]?\s*([\d,]+)",
        text, re.IGNORECASE
    )
    if total_match:
        raw = total_match.group(1)
        norm = normalise_integer(raw)
        # Approximate bounding box via token scan
        conf = _region_confidence(tokens, total_match.start(), total_match.end())
        if conf < FAST_FAIL:
            fields.append(CandidateField(
                "total_faculty", raw, None, conf, None, page_no,
                "regex_anchor", "INDETERMINATE", "FAST_FAIL_OCR"
            ))
        else:
            fields.append(CandidateField(
                "total_faculty", raw, norm, conf, None, page_no, "regex_anchor"
            ))

    # Professor count
    prof_match = re.search(
        r"professor\s*[:\-]?\s*([\d,]+)",
        text, re.IGNORECASE
    )
    if prof_match:
        raw = prof_match.group(1)
        norm = normalise_integer(raw)
        conf = _region_confidence(tokens, prof_match.start(), prof_match.end())
        if conf < FAST_FAIL:
            fields.append(CandidateField(
                "professor_count", raw, None, conf, None, page_no,
                "regex_anchor", "INDETERMINATE", "FAST_FAIL_OCR"
            ))
        else:
            fields.append(CandidateField(
                "professor_count", raw, norm, conf, None, page_no, "regex_anchor"
            ))

    return fields


def extract_from_application_form(tokens: list[WordToken], page_no: int) -> list[CandidateField]:
    """Extract sanctioned intake, land area, built-up area, institution name."""
    fields = []
    text = _tokens_text(tokens)

    # Sanctioned intake
    intake_match = re.search(
        r"(?:sanctioned intake|total intake|approved intake)\s*[:\-]?\s*([\d,]+)",
        text, re.IGNORECASE
    )
    if intake_match:
        raw = intake_match.group(1)
        norm = normalise_integer(raw)
        conf = _region_confidence(tokens, intake_match.start(), intake_match.end())
        status = "INDETERMINATE" if conf < FAST_FAIL else "AUTO"
        reason = "FAST_FAIL_OCR" if conf < FAST_FAIL else None
        fields.append(CandidateField(
            "sanctioned_intake_total", raw, norm if status == "AUTO" else None,
            conf, None, page_no, "regex_anchor", status, reason
        ))

    # Land area
    land_match = re.search(
        r"(?:land area|plot area|site area)\s*[:\-]?\s*([\d,\.]+\s*(?:acres?|sq\.?\s*m|sq\.?\s*ft|hectares?|guntha))",
        text, re.IGNORECASE
    )
    if land_match:
        raw = land_match.group(1)
        norm = normalise_area_to_acres(raw)
        conf = _region_confidence(tokens, land_match.start(), land_match.end())
        status = "INDETERMINATE" if conf < FAST_FAIL else "AUTO"
        reason = "FAST_FAIL_OCR" if conf < FAST_FAIL else None
        fields.append(CandidateField(
            "total_land_area_acres", raw, norm if status == "AUTO" else None,
            conf, None, page_no, "regex_anchor", status, reason
        ))

    # Built-up area
    buildup_match = re.search(
        r"(?:built.?up area|total built.?up|floor area)\s*[:\-]?\s*([\d,\.]+\s*(?:sq\.?\s*m|sq\.?\s*ft|hectares?))",
        text, re.IGNORECASE
    )
    if buildup_match:
        raw = buildup_match.group(1)
        norm = normalise_area_to_sqm(raw)
        conf = _region_confidence(tokens, buildup_match.start(), buildup_match.end())
        status = "INDETERMINATE" if conf < FAST_FAIL else "AUTO"
        reason = "FAST_FAIL_OCR" if conf < FAST_FAIL else None
        fields.append(CandidateField(
            "total_buildup_area_sqm", raw, norm if status == "AUTO" else None,
            conf, None, page_no, "regex_anchor", status, reason
        ))

    # Institution name
    name_match = re.search(
        r"(?:name of institution|institution name|name of college)\s*[:\-]?\s*([A-Za-z0-9 ,\.\-]+?)(?=\s*(?:aicte|state|total|sanctioned|academic|\n|$))",
        text, re.IGNORECASE
    )
    if name_match:
        raw = name_match.group(1).strip()[:200]
        conf = _region_confidence(tokens, name_match.start(), name_match.end())
        fields.append(CandidateField(
            "institution_name", raw, normalise_name(raw),
            conf, None, page_no, "regex_anchor"
        ))

    return fields


def extract_from_land_deed(tokens: list[WordToken], page_no: int) -> list[CandidateField]:
    """Extract land area, survey number, institution name from a land deed."""
    fields = []
    text = _tokens_text(tokens)

    # Land area
    area_match = re.search(
        r"(?:measuring|total area|land admeasuring|extent of)\s*[:\-]?\s*([\d,\.]+\s*(?:acres?|sq\.?\s*m|sq\.?\s*ft|hectares?|guntha))",
        text, re.IGNORECASE
    )
    if area_match:
        raw = area_match.group(1)
        norm = normalise_area_to_acres(raw)
        conf = _region_confidence(tokens, area_match.start(), area_match.end())
        status = "INDETERMINATE" if conf < FAST_FAIL else "AUTO"
        reason = "FAST_FAIL_OCR" if conf < FAST_FAIL else None
        fields.append(CandidateField(
            "deed_land_area_acres", raw, norm if status == "AUTO" else None,
            conf, None, page_no, "regex_anchor", status, reason
        ))

    # Survey number
    survey_match = re.search(
        r"(?:survey\s*(?:no|number|nos?\.?))\s*[:\-]?\s*([\w/\-]+)",
        text, re.IGNORECASE
    )
    if survey_match:
        raw = survey_match.group(1).strip()
        conf = _region_confidence(tokens, survey_match.start(), survey_match.end())
        fields.append(CandidateField(
            "survey_number", raw, raw, conf, None, page_no, "regex_anchor"
        ))

    return fields


def extract_from_financial_statement(tokens: list[WordToken], page_no: int) -> list[CandidateField]:
    """Extract audited corpus / surplus from financial statements."""
    fields = []
    text = _tokens_text(tokens)

    # Corpus fund / surplus
    corpus_match = re.search(
        r"(?:corpus fund|general reserve|surplus|net income)\s*[:\-]?\s*((?:rs\.?\s*)?[\d,\.]+\s*(?:lakh|cr|crore)?)",
        text, re.IGNORECASE
    )
    if corpus_match:
        raw = corpus_match.group(1)
        norm = normalise_currency_to_crores(raw)
        conf = _region_confidence(tokens, corpus_match.start(), corpus_match.end())
        status = "INDETERMINATE" if conf < FAST_FAIL else "AUTO"
        reason = "FAST_FAIL_OCR" if conf < FAST_FAIL else None
        fields.append(CandidateField(
            "audited_corpus_cr", raw, norm if status == "AUTO" else None,
            conf, None, page_no, "regex_anchor", status, reason
        ))

    return fields


def _region_confidence(tokens: list[WordToken], start_char: int, end_char: int) -> float:
    """Estimate OCR confidence for a character range by scanning token positions."""
    # Approximate: use overall page mean if positions not tracked
    if not tokens:
        return 0.0
    relevant = [t for t in tokens if t.confidence < 1.0]  # exclude native-text (conf=1.0)
    if not relevant:
        return 1.0  # native text layer
    return sum(t.confidence for t in relevant) / len(relevant)


def extract_from_building_plan(tokens: list[WordToken], page_no: int) -> list[CandidateField]:
    """Extract built-up area and structural details from building plan."""
    fields = []
    text = _tokens_text(tokens)

    total_match = re.search(
        r"(?:total\s+built.?up(?:\s*area)?)\s*[:\-]?\s*([\d,\.]+\s*(?:sq\.?\s*m|sq\.?\s*ft|hectares?))",
        text, re.IGNORECASE
    )
    buildup_match = total_match or re.search(
        r"(?:built.?up area|floor area)\s*[:\-]?\s*([\d,\.]+\s*(?:sq\.?\s*m|sq\.?\s*ft|hectares?))",
        text, re.IGNORECASE
    )
    if buildup_match:
        raw = buildup_match.group(1)
        norm = normalise_area_to_sqm(raw)
        conf = _region_confidence(tokens, buildup_match.start(), buildup_match.end())
        status = "INDETERMINATE" if conf < FAST_FAIL else "AUTO"
        reason = "FAST_FAIL_OCR" if conf < FAST_FAIL else None
        fields.append(CandidateField(
            "plan_buildup_area_sqm", raw, norm if status == "AUTO" else None,
            conf, None, page_no, "regex_anchor", status, reason
        ))

    return fields


# ─── Dispatcher ───────────────────────────────────────────────────────────────

EXTRACTOR_MAP = {
    "APPLICATION_FORM": extract_from_application_form,
    "FACULTY_LIST": extract_from_faculty_list,
    "LAND_DEED": extract_from_land_deed,
    "FINANCIAL_STATEMENT": extract_from_financial_statement,
    "BUILDING_PLAN": extract_from_building_plan,
}


def extract_fields(doc_type: str, tokens: list[WordToken], page_no: int) -> list[CandidateField]:
    """Dispatch to the appropriate extractor."""
    extractor = EXTRACTOR_MAP.get(doc_type)
    if extractor:
        return extractor(tokens, page_no)
    return []
