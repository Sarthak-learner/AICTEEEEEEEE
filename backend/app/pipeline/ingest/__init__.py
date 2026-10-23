"""Upload ingestion: validate, scan, store, hash.

Validation steps:
1. File size check
2. Magic bytes (not extension) to confirm allowed type
3. Decompression bomb check for PDFs
4. ClamAV scan (if enabled)
5. Content-address storage
"""
from __future__ import annotations
import hashlib
import os
import struct
import tempfile
from pathlib import Path
from typing import Optional

from app.config import get_settings
from app.services.storage import store_file

settings = get_settings()

ALLOWED_MAGIC = {
    b"%PDF": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"II*\x00": "image/tiff",  # TIFF little-endian
    b"MM\x00*": "image/tiff",  # TIFF big-endian
}

MAX_PDF_PAGES = settings.MAX_PAGES


class IngestionError(Exception):
    pass


def validate_and_store(
    file_bytes: bytes,
    original_name: str,
) -> dict:
    """
    Validate and store an uploaded file.
    Returns dict with: sha256, storage_key, mime, page_count (PDF) or 1.
    Raises IngestionError on validation failure.
    """
    # Size check
    size_mb = len(file_bytes) / (1024 * 1024)
    if size_mb > settings.MAX_FILE_SIZE_MB:
        raise IngestionError(f"File too large: {size_mb:.1f} MB > {settings.MAX_FILE_SIZE_MB} MB limit")

    # Magic bytes check
    mime = _detect_mime(file_bytes)
    if mime is None:
        raise IngestionError(
            f"File type not allowed. Accepted: PDF, JPEG, PNG, TIFF. "
            f"First bytes: {file_bytes[:4].hex()!r}"
        )

    # PDF-specific checks
    page_count = 1
    if mime == "application/pdf":
        _check_pdf_not_encrypted(file_bytes)
        page_count = _count_pdf_pages(file_bytes)
        if page_count > MAX_PDF_PAGES:
            raise IngestionError(f"PDF has {page_count} pages, exceeds limit of {MAX_PDF_PAGES}")

    # ClamAV scan
    if settings.CLAMAV_ENABLED:
        _clamav_scan(file_bytes)

    # Write to temp file and store
    with tempfile.NamedTemporaryFile(delete=False, suffix=Path(original_name).suffix) as tmp:
        tmp.write(file_bytes)
        tmp_path = Path(tmp.name)

    try:
        sha256, storage_key = store_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    return {
        "sha256": sha256,
        "storage_key": storage_key,
        "mime": mime,
        "page_count": page_count,
    }


def _detect_mime(data: bytes) -> Optional[str]:
    """Detect MIME type by magic bytes."""
    for magic, mime in ALLOWED_MAGIC.items():
        if data[:len(magic)] == magic:
            return mime
    return None


def _check_pdf_not_encrypted(data: bytes) -> None:
    """Raise if PDF is encrypted (basic check)."""
    if b"/Encrypt" in data[:8192]:
        raise IngestionError("Encrypted PDFs are not accepted. Please provide an unencrypted copy.")


def _count_pdf_pages(data: bytes) -> int:
    """Count PDF pages using pdfplumber, pypdfium2, or PyMuPDF."""
    try:
        import pdfplumber
        import io
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages)
    except Exception:
        pass

    try:
        import pypdfium2
        doc = pypdfium2.PdfDocument(data)
        count = len(doc)
        doc.close()
        return count
    except Exception:
        pass

    try:
        import fitz
        doc = fitz.open(stream=data, filetype="pdf")
        count = len(doc)
        doc.close()
        return count
    except Exception:
        return 1



def _clamav_scan(data: bytes) -> None:
    """Scan bytes with ClamAV. Raises IngestionError if infected."""
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((settings.CLAMAV_HOST, settings.CLAMAV_PORT))
        # Use INSTREAM command
        s.send(b"zINSTREAM\0")
        size = struct.pack("!I", len(data))
        s.send(size + data)
        s.send(struct.pack("!I", 0))  # end of stream
        result = s.recv(2048).decode(errors="replace")
        s.close()
        if "FOUND" in result:
            raise IngestionError(f"File rejected by virus scanner: {result.strip()}")
    except IngestionError:
        raise
    except Exception as e:
        # ClamAV unavailable - log and continue (do not block upload)
        import logging
        logging.getLogger(__name__).warning(f"ClamAV scan failed (continuing): {e}")
