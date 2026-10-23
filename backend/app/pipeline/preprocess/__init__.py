"""Image preprocessing module for scanned documents and plans.

Functions:
- deskew: calculate skew angle and rotate image
- binarize: adaptive or Otsu thresholding
- estimate_blur: Laplacian variance to detect unreadable blurry scans
- preprocess_image: full pipeline (grayscale, deskew, denoise, binarize)
"""
from __future__ import annotations
import math
from typing import Tuple, Optional
import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


def estimate_blur(image: np.ndarray) -> float:
    """Compute variance of the Laplacian as a blur indicator.
    
    Low values (< 100.0) typically indicate blurry images that may fast-fail OCR.
    """
    if not CV2_AVAILABLE:
        return 999.0
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def deskew(image: np.ndarray) -> Tuple[np.ndarray, float]:
    """Deskew image using minimum area bounding box of text contours.
    
    Returns (deskewed_image, angle_degrees).
    """
    if not CV2_AVAILABLE:
        return image, 0.0

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    # Invert and threshold to get text pixels
    thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

    # Find coordinates of all white pixels (text)
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) < 50:
        return image, 0.0

    angle = cv2.minAreaRect(coords)[-1]
    # minAreaRect returns angle in [-90, 0)
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle

    # Don't rotate if angle is negligible or extreme
    if abs(angle) < 0.5 or abs(angle) > 45:
        return image, 0.0

    (h, w) = image.shape[:2]
    center = (w // 2, h // 2)
    m = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(
        image, m, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE
    )
    return rotated, angle


def binarize(gray: np.ndarray, method: str = "otsu") -> np.ndarray:
    """Binarize grayscale image using Otsu or adaptive Gaussian thresholding."""
    if not CV2_AVAILABLE:
        return gray
    if method == "adaptive":
        return cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, 11, 2
        )
    return cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Full preprocessing pipeline: convert to grayscale, deskew, and binarize."""
    if not CV2_AVAILABLE:
        return image
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image

    deskewed, _ = deskew(gray)
    denoised = cv2.medianBlur(deskewed, 3)
    binarized = binarize(denoised, method="otsu")
    return binarized
