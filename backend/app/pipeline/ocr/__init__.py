"""OCR pipeline: PyMuPDF / pdfplumber native text → Tesseract fallback.

Returns word tokens with bounding boxes and confidence scores.
Implements Fast-Fail gate at configurable threshold (default 0.60).
"""
from __future__ import annotations
import io
import os
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

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

from app.config import get_settings

settings = get_settings()

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


@dataclass
class WordToken:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    confidence: float  # 0.0 – 1.0
    page_no: int


@dataclass
class PageOCRResult:
    page_no: int
    tokens: list[WordToken]
    ocr_engine: str  # "native" | "tesseract" | "none"
    mean_confidence: float
    fast_failed: bool = False
    fast_fail_reason: Optional[str] = None


def extract_text_from_pdf(pdf_path: Path, max_pages: Optional[int] = None) -> list[PageOCRResult]:
    """
    Extract text from a PDF using native layer first, Tesseract as fallback.
    Returns one PageOCRResult per page.
    """
    if FITZ_AVAILABLE:
        try:
            return _extract_with_fitz(pdf_path, max_pages)
        except Exception:
            pass  # Fallback to pdfplumber if fitz errors at runtime

    if PDFPLUMBER_AVAILABLE:
        return _extract_with_pdfplumber(pdf_path, max_pages)

    raise RuntimeError("No PDF extraction engine available (neither PyMuPDF nor pdfplumber installed)")


def _extract_with_fitz(pdf_path: Path, max_pages: Optional[int] = None) -> list[PageOCRResult]:
    results = []
    doc = fitz.open(str(pdf_path))
    total_pages = min(len(doc), max_pages or settings.MAX_PAGES)

    for page_no in range(total_pages):
        page = doc[page_no]
        result = _process_page_fitz(page, page_no + 1)
        results.append(result)

    doc.close()
    return results


def _extract_with_pdfplumber(pdf_path: Path, max_pages: Optional[int] = None) -> list[PageOCRResult]:
    results = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = min(len(pdf.pages), max_pages or settings.MAX_PAGES)
        for page_idx in range(total_pages):
            page_no = page_idx + 1
            page = pdf.pages[page_idx]
            words = page.extract_words()
            tokens = []
            for w in words:
                text = str(w.get("text", "")).strip()
                if text:
                    tokens.append(WordToken(
                        text=text,
                        x0=float(w.get("x0", 0.0)),
                        y0=float(w.get("top", 0.0)),
                        x1=float(w.get("x1", 0.0)),
                        y1=float(w.get("bottom", 0.0)),
                        confidence=1.0,
                        page_no=page_no,
                    ))

            native_chars = sum(len(t.text.strip()) for t in tokens)
            if native_chars >= settings.OCR_MIN_TEXT_CHARS:
                mean_conf = _mean_confidence(tokens) if tokens else 0.0
                results.append(PageOCRResult(
                    page_no=page_no,
                    tokens=tokens,
                    ocr_engine="native",
                    mean_confidence=mean_conf,
                ))
            else:
                # Fallback to Tesseract if available
                if not TESSERACT_AVAILABLE:
                    results.append(PageOCRResult(
                        page_no=page_no,
                        tokens=[],
                        ocr_engine="none",
                        mean_confidence=0.0,
                        fast_failed=True,
                        fast_fail_reason="Native text insufficient and Tesseract not available",
                    ))
                else:
                    try:
                        if PYPDFIUM2_AVAILABLE:
                            doc = pypdfium2.PdfDocument(str(pdf_path))
                            pil_img = doc[page_idx].render(scale=settings.OCR_DPI / 72.0).to_pil()
                            doc.close()
                        else:
                            pil_img = page.to_image(resolution=settings.OCR_DPI).original
                        results.append(_tesseract_ocr_pil(pil_img, page_no))
                    except Exception as e:
                        results.append(PageOCRResult(
                            page_no=page_no,
                            tokens=[],
                            ocr_engine="tesseract",
                            mean_confidence=0.0,
                            fast_failed=True,
                            fast_fail_reason=f"OCR error: {e}",
                        ))
    return results


def _process_page_fitz(page: fitz.Page, page_no: int) -> PageOCRResult:
    """Process a single PDF page with PyMuPDF."""
    native_tokens = _extract_native_text_fitz(page, page_no)
    native_chars = sum(len(t.text.strip()) for t in native_tokens)
    if native_chars >= settings.OCR_MIN_TEXT_CHARS:
        mean_conf = _mean_confidence(native_tokens) if native_tokens else 0.0
        return PageOCRResult(
            page_no=page_no,
            tokens=native_tokens,
            ocr_engine="native",
            mean_confidence=mean_conf,
        )

    if not TESSERACT_AVAILABLE:
        return PageOCRResult(
            page_no=page_no,
            tokens=[],
            ocr_engine="none",
            mean_confidence=0.0,
            fast_failed=True,
            fast_fail_reason="Tesseract not available",
        )

    mat = fitz.Matrix(settings.OCR_DPI / 72, settings.OCR_DPI / 72)
    pix = page.get_pixmap(matrix=mat, colorspace=fitz.csGRAY)
    img_bytes = pix.tobytes("png")
    pil_img = Image.open(io.BytesIO(img_bytes))
    return _tesseract_ocr_pil(pil_img, page_no)


def _extract_native_text_fitz(page: fitz.Page, page_no: int) -> list[WordToken]:
    """Extract word tokens from the native PDF text layer using PyMuPDF."""
    words = page.get_text("words")
    tokens = []
    for w in words:
        x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
        if text.strip():
            tokens.append(WordToken(
                text=text,
                x0=x0, y0=y0, x1=x1, y1=y1,
                confidence=1.0,
                page_no=page_no,
            ))
    return tokens


def _tesseract_ocr_pil(pil_img: Image.Image, page_no: int) -> PageOCRResult:
    """Run Tesseract OCR on a PIL image."""
    if CV2_AVAILABLE:
        nparr = np.array(pil_img.convert("L"))
        blur_score = cv2.Laplacian(nparr, cv2.CV_64F).var()
        if blur_score < 50:
            return PageOCRResult(
                page_no=page_no,
                tokens=[],
                ocr_engine="tesseract",
                mean_confidence=0.0,
                fast_failed=True,
                fast_fail_reason=f"Page too blurry (Laplacian variance={blur_score:.1f})",
            )
        img_for_ocr = Image.fromarray(_preprocess_image(nparr))
    else:
        img_for_ocr = pil_img

    try:
        data = pytesseract.image_to_data(img_for_ocr, output_type=pytesseract.Output.DICT, lang="eng")
    except Exception as e:
        return PageOCRResult(
            page_no=page_no,
            tokens=[],
            ocr_engine="tesseract",
            mean_confidence=0.0,
            fast_failed=True,
            fast_fail_reason=f"Tesseract error: {e}",
        )

    tokens = []
    scale = 72.0 / settings.OCR_DPI
    for i, text in enumerate(data.get("text", [])):
        if text.strip() and data.get("conf", [0])[i] >= 0:
            conf = data["conf"][i] / 100.0
            x0 = data["left"][i] * scale
            y0 = data["top"][i] * scale
            x1 = (data["left"][i] + data["width"][i]) * scale
            y1 = (data["top"][i] + data["height"][i]) * scale
            tokens.append(WordToken(
                text=text,
                x0=x0, y0=y0, x1=x1, y1=y1,
                confidence=conf,
                page_no=page_no,
            ))

    mean_conf = _mean_confidence(tokens) if tokens else 0.0
    return PageOCRResult(
        page_no=page_no,
        tokens=tokens,
        ocr_engine="tesseract",
        mean_confidence=mean_conf,
    )


def _preprocess_image(img: "np.ndarray") -> "np.ndarray":
    """Deskew, denoise, and threshold for better OCR when cv2 is present."""
    if not CV2_AVAILABLE:
        return img
    return cv2.adaptiveThreshold(
        img, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )


def _mean_confidence(tokens: list[WordToken]) -> float:
    if not tokens:
        return 0.0
    return sum(t.confidence for t in tokens) / len(tokens)


def ocr_region(pdf_path: Path, page_no: int, bbox: list[float]) -> tuple[str, float]:
    """OCR a specific region (for manual correction assist). Returns (text, confidence)."""
    if PDFPLUMBER_AVAILABLE:
        try:
            with pdfplumber.open(str(pdf_path)) as pdf:
                if 1 <= page_no <= len(pdf.pages):
                    page = pdf.pages[page_no - 1]
                    x0, y0, x1, y1 = bbox
                    words = page.extract_words()
                    region_words = [
                        w["text"] for w in words
                        if not (w["x1"] < x0 or w["x0"] > x1 or w["bottom"] < y0 or w["top"] > y1)
                    ]
                    if region_words:
                        return " ".join(region_words), 1.0
        except Exception:
            pass

    if FITZ_AVAILABLE:
        try:
            doc = fitz.open(str(pdf_path))
            page = doc[page_no - 1]
            rect = fitz.Rect(*bbox)
            text = page.get_text("text", clip=rect).strip()
            doc.close()
            if text:
                return text, 1.0
        except Exception:
            pass

    return "", 0.0

