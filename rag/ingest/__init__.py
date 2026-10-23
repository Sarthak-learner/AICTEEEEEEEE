"""Ingestion module for official regulatory publications (AICTE APH, Corrigenda)."""
from pathlib import Path
import hashlib
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


def ingest_regulatory_document(pdf_path: Path) -> dict:
    """Read official PDF document, hash contents, and extract text pages."""
    if not pdf_path.exists():
        raise FileNotFoundError(f"File not found: {pdf_path}")

    with open(pdf_path, "rb") as f:
        data = f.read()
    sha256 = hashlib.sha256(data).hexdigest()

    pages_text = []
    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(str(pdf_path))
            for page_no in range(len(doc)):
                page = doc[page_no]
                pages_text.append({
                    "page_no": page_no + 1,
                    "text": page.get_text()
                })
            doc.close()
        except Exception:
            pages_text = []

    if not pages_text and PDFPLUMBER_AVAILABLE:
        with pdfplumber.open(str(pdf_path)) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                pages_text.append({
                    "page_no": page_idx + 1,
                    "text": page.extract_text() or ""
                })


    return {
        "filename": pdf_path.name,
        "sha256": sha256,
        "page_count": len(pages_text),
        "pages": pages_text,
    }
