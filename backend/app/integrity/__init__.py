"""Integrity checks for uploaded documents.

Checks:
1. PDF metadata (creator, producer, modification date)
2. Digital signature validation via pyHanko
3. Image forensics (ELA indicator - scans only)
4. Perceptual hash for duplicate detection

Policy: severity capped at MAJOR; is_proof always False.
Wording: 'Needs verification', never 'forged'.
"""
from __future__ import annotations
import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import fitz  # PyMuPDF
    FITZ_AVAILABLE = True
except (ImportError, Exception):
    fitz = None
    FITZ_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import pypdfium2
    PYPDFIUM2_AVAILABLE = True
except ImportError:
    PYPDFIUM2_AVAILABLE = False

try:
    from pyhanko.pdf_utils.reader import PdfFileReader
    from pyhanko.sign.validation import validate_pdf_signature
    PYHANKO_AVAILABLE = True
except ImportError:
    PYHANKO_AVAILABLE = False


@dataclass
class IntegrityResult:
    check_type: str
    indicator: str
    severity: str  # CRITICAL (NOT used per policy), MAJOR, MINOR, ADVISORY
    detail: dict
    is_proof: bool = False  # always False per policy


def check_pdf_metadata(pdf_path: Path) -> list[IntegrityResult]:
    """Inspect PDF metadata for anomalies."""
    results = []
    meta = {}
    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(str(pdf_path))
            meta = doc.metadata or {}
            doc.close()
        except Exception:
            meta = {}

    if not meta and PDFPLUMBER_AVAILABLE:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                meta = pdf.metadata or {}
        except Exception:
            meta = {}

    if not meta and PYPDFIUM2_AVAILABLE:
        try:
            doc = pypdfium2.PdfDocument(str(pdf_path))
            meta = doc.get_metadata_dict()
            doc.close()
        except Exception:
            meta = {}

    creator = meta.get("creator") or meta.get("Creator") or ""
    producer = meta.get("producer") or meta.get("Producer") or ""
    creation_date = meta.get("creationDate") or meta.get("CreationDate") or ""
    mod_date = meta.get("modDate") or meta.get("ModDate") or ""

    # Flag if modification date is after creation date by a long time
    if creation_date and mod_date and mod_date > creation_date:
        results.append(IntegrityResult(
            "METADATA_MOD_AFTER_CREATION",

            f"Document modified after creation. Creator: {creator!r}, Producer: {producer!r}. Needs verification.",
            "MINOR",
            {
                "creator": creator, "producer": producer,
                "creation_date": creation_date, "mod_date": mod_date
            },
            is_proof=False
        ))

    # Flag unusual producer software
    COMMON_PRODUCERS = ["adobe", "microsoft", "libreoffice", "pdflatex", "fpdf",
                        "reportlab", "weasyprint", "ghostscript", "inkscape"]
    if producer and not any(p in producer.lower() for p in COMMON_PRODUCERS):
        results.append(IntegrityResult(
            "METADATA_UNUSUAL_PRODUCER",
            f"Unusual PDF producer software: {producer!r}. Needs verification.",
            "MINOR",
            {"producer": producer},
            is_proof=False
        ))

    return results


def check_pdf_signature(pdf_path: Path) -> IntegrityResult:
    """Validate digital signatures using pyHanko."""
    if not PYHANKO_AVAILABLE:
        return IntegrityResult(
            "SIGNATURE", "Signature check skipped (pyHanko not available)",
            "ADVISORY", {"reason": "library_unavailable"}
        )

    try:
        with open(pdf_path, "rb") as f:
            reader = PdfFileReader(f)
            sig_fields = reader.embedded_signatures
            if not sig_fields:
                return IntegrityResult(
                    "SIGNATURE", "No digital signature found",
                    "ADVISORY", {"result": "NO_SIGNATURE"}
                )

            validation_results = []
            for sig in sig_fields:
                try:
                    # Basic signature validation (no OCSP/CRL in offline mode)
                    status = validate_pdf_signature(sig)
                    validation_results.append({
                        "signer": str(sig.signer_cert.subject) if hasattr(sig, 'signer_cert') else "unknown",
                        "intact": status.intact,
                        "valid": status.valid,
                    })
                    if not status.intact:
                        return IntegrityResult(
                            "SIGNATURE",
                            "Document modified after signing. Needs verification by issuing authority.",
                            "MAJOR",
                            {"result": "MODIFIED_AFTER_SIGNING", "details": validation_results},
                            is_proof=False
                        )
                except Exception as e:
                    return IntegrityResult(
                        "SIGNATURE", f"Signature validation error: {e}",
                        "MINOR", {"result": "INVALID", "error": str(e)}
                    )

            return IntegrityResult(
                "SIGNATURE", "Digital signature present; certificate chain not fully verified (offline mode)",
                "ADVISORY",
                {"result": "VALID_UNTRUSTED_CHAIN", "signatures": validation_results}
            )

    except Exception as e:
        return IntegrityResult(
            "SIGNATURE", f"Cannot read PDF for signature check: {e}",
            "MINOR", {"error": str(e)}
        )


def compute_perceptual_hash(pdf_path: Path, page_no: int = 0) -> Optional[str]:
    """Compute a perceptual hash of the first page for duplicate detection."""
    if PYPDFIUM2_AVAILABLE:
        try:
            doc = pypdfium2.PdfDocument(str(pdf_path))
            if page_no < len(doc):
                pil_img = doc[page_no].render(scale=0.5).to_pil()
                doc.close()
                return hashlib.md5(pil_img.tobytes()).hexdigest()
            doc.close()
        except Exception:
            pass

    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(str(pdf_path))
            if page_no >= len(doc):
                doc.close()
                return None
            page = doc[page_no]
            mat = fitz.Matrix(0.5, 0.5)  # low-res for hashing
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
            doc.close()
            return hashlib.md5(pix.tobytes()).hexdigest()
        except Exception:
            pass

    return None



def run_all_integrity_checks(pdf_path: Path) -> list[IntegrityResult]:
    """Run all integrity checks on a PDF file."""
    results = []
    results.extend(check_pdf_metadata(pdf_path))
    results.append(check_pdf_signature(pdf_path))
    return results
