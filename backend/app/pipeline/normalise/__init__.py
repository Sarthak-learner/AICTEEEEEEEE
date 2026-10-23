"""Normaliser: convert raw extracted values to typed, canonical form.

Handles:
- Area units: sq ft, sq m, acres, hectares, guntha → sq m and acres
- Currency: lakh, crore → base rupees (stored as float with unit label)
- Indian number format: 1,00,000 → 100000
- Names: lower-case, strip titles/punctuation
- Dates: various Indian formats → ISO 8601
"""
from __future__ import annotations
import re
from typing import Any, Optional
from dataclasses import dataclass


@dataclass
class NormalisedValue:
    value: Any  # typed value
    unit: Optional[str]  # canonical unit string
    raw: str  # original string
    valid: bool = True
    error: Optional[str] = None


# ─── Area normalisation ───────────────────────────────────────────────────────

# 1 acre = 4046.856 sq m
# 1 sq ft = 0.0929 sq m
# 1 hectare = 10000 sq m
# 1 guntha = 101.17 sq m

AREA_TO_SQM = {
    "sq m": 1.0,
    "sqm": 1.0,
    "square metre": 1.0,
    "square meter": 1.0,
    "sq ft": 0.0929,
    "sqft": 0.0929,
    "square foot": 0.0929,
    "square feet": 0.0929,
    "acre": 4046.856,
    "acres": 4046.856,
    "hectare": 10000.0,
    "hectares": 10000.0,
    "guntha": 101.17,
    "gunta": 101.17,
}

AREA_TO_ACRES = {k: v / 4046.856 for k, v in AREA_TO_SQM.items()}


def normalise_area_to_sqm(raw: str) -> NormalisedValue:
    """Parse area string and return value in sq m."""
    raw = raw.strip()
    match = re.search(
        r"([\d,\.]+)\s*(" + "|".join(re.escape(k) for k in AREA_TO_SQM) + r")",
        raw, re.IGNORECASE
    )
    if not match:
        return NormalisedValue(None, "sq m", raw, False, f"Cannot parse area: {raw!r}")
    number_str = match.group(1).replace(",", "")
    unit_str = match.group(2).lower().strip()
    try:
        number = float(number_str)
    except ValueError:
        return NormalisedValue(None, "sq m", raw, False, f"Cannot parse number: {number_str!r}")
    factor = AREA_TO_SQM.get(unit_str, 1.0)
    return NormalisedValue(number * factor, "sq m", raw)


def normalise_area_to_acres(raw: str) -> NormalisedValue:
    """Parse area string and return value in acres."""
    result = normalise_area_to_sqm(raw)
    if not result.valid or result.value is None:
        return result
    return NormalisedValue(result.value / 4046.856, "acres", raw)


# ─── Currency normalisation ───────────────────────────────────────────────────

CURRENCY_MULTIPLIER = {
    "lakh": 1e5,
    "lakhs": 1e5,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
}


def normalise_currency(raw: str) -> NormalisedValue:
    """Parse Indian currency (lakh/crore) to a base rupee float plus label."""
    raw = raw.strip()
    # Remove Rs / INR prefix
    cleaned = re.sub(r"(?i)rs\.?\s*|inr\s*|₹\s*", "", raw).strip()
    # Check for multiplier
    mult_match = re.search(
        r"([\d,\.]+)\s*(" + "|".join(re.escape(k) for k in CURRENCY_MULTIPLIER) + r")",
        cleaned, re.IGNORECASE
    )
    if mult_match:
        number_str = mult_match.group(1).replace(",", "")
        unit = mult_match.group(2).lower()
        try:
            number = float(number_str)
        except ValueError:
            return NormalisedValue(None, "INR", raw, False, f"Cannot parse: {number_str}")
        multiplier = CURRENCY_MULTIPLIER[unit]
        label = "crores" if "cr" in unit else "lakhs"
        return NormalisedValue(number * multiplier, label, raw)

    # Plain number
    num_match = re.search(r"([\d,\.]+)", cleaned)
    if num_match:
        try:
            return NormalisedValue(float(num_match.group(1).replace(",", "")), "INR", raw)
        except ValueError:
            pass
    return NormalisedValue(None, "INR", raw, False, f"Cannot parse currency: {raw!r}")


def normalise_currency_to_crores(raw: str) -> NormalisedValue:
    """Normalise currency and return value in crores."""
    result = normalise_currency(raw)
    if not result.valid or result.value is None:
        return result
    return NormalisedValue(result.value / 1e7, "crores", raw)


# ─── Integer count normalisation ──────────────────────────────────────────────

def normalise_integer(raw: str) -> NormalisedValue:
    """Parse an Indian-formatted integer."""
    cleaned = raw.strip().replace(",", "")
    match = re.search(r"(\d+)", cleaned)
    if not match:
        return NormalisedValue(None, "count", raw, False, f"No integer found: {raw!r}")
    return NormalisedValue(int(match.group(1)), "count", raw)


# ─── Name normalisation ───────────────────────────────────────────────────────

TITLES = re.compile(
    r"\b(mr|mrs|ms|dr|prof|shri|smt|kum|er)\b\.?",
    re.IGNORECASE
)


def normalise_name(raw: str) -> str:
    """Lower-case name, strip titles and punctuation."""
    name = TITLES.sub("", raw)
    # Remove dots from single-letter abbreviations/initials (e.g. A.B. -> AB)
    name = re.sub(r"(?<=\b[A-Za-z])\.(?=\s*[A-Za-z]\b|\s|$)", "", name)
    name = re.sub(r"[^\w\s]", " ", name)
    name = " ".join(name.split())
    return name.lower().strip()


# ─── Date normalisation ───────────────────────────────────────────────────────

def normalise_date(raw: str) -> Optional[str]:
    """Parse common Indian date formats to ISO 8601 (YYYY-MM-DD)."""
    raw = raw.strip()
    # DD/MM/YYYY or DD-MM-YYYY
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", raw)
    if m:
        d, mo, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{int(mo):02d}-{int(d):02d}"
    # YYYY-MM-DD already
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return None
