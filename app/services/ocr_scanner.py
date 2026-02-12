"""OCR-based text extraction from video frames using pytesseract."""

import logging

import cv2
import numpy as np
import pytesseract

from app.services.code_validator import extract_codes_from_text, apply_ocr_corrections

logger = logging.getLogger(__name__)

# Tesseract config for alphanumeric code reading
TESSERACT_CONFIG = (
    "--oem 3 --psm 6 "
    "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
)

# Config for single line / single word
TESSERACT_CONFIG_SINGLE = (
    "--oem 3 --psm 7 "
    "-c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-"
)


def scan_frame_for_text_codes(frame: np.ndarray) -> list[str]:
    """Scan a video frame for Pokemon TCG codes using OCR.

    Uses multiple preprocessing strategies to maximize detection.

    Args:
        frame: BGR image as numpy array

    Returns:
        List of normalized codes found via OCR
    """
    all_codes = set()

    # Convert to grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Strategy 1: Basic grayscale OCR
    codes = _ocr_and_extract(gray, TESSERACT_CONFIG)
    all_codes.update(codes)

    # Strategy 2: Otsu's thresholding
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    codes = _ocr_and_extract(otsu, TESSERACT_CONFIG)
    all_codes.update(codes)

    # Strategy 3: Adaptive threshold
    adaptive = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    codes = _ocr_and_extract(adaptive, TESSERACT_CONFIG)
    all_codes.update(codes)

    # Strategy 4: Inverted (white text on dark background)
    inverted = cv2.bitwise_not(gray)
    codes = _ocr_and_extract(inverted, TESSERACT_CONFIG)
    all_codes.update(codes)

    # Strategy 5: Enhanced contrast + sharpen
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    sharpened = cv2.filter2D(enhanced, -1, kernel)
    codes = _ocr_and_extract(sharpened, TESSERACT_CONFIG)
    all_codes.update(codes)

    return list(all_codes)


def _ocr_and_extract(image: np.ndarray, config: str) -> list[str]:
    """Run OCR on an image and extract any Pokemon TCG codes."""
    try:
        text = pytesseract.image_to_string(image, config=config)
        if not text.strip():
            return []

        # Apply OCR corrections
        corrected = apply_ocr_corrections(text)

        # Extract codes
        return extract_codes_from_text(corrected)
    except Exception as e:
        logger.debug(f"OCR error: {e}")
        return []


def scan_region_for_code(frame: np.ndarray, x: int, y: int, w: int, h: int) -> list[str]:
    """Scan a specific region of a frame for codes.

    Useful when we know roughly where a code card might be.
    """
    # Add some padding
    pad = 20
    y1 = max(0, y - pad)
    y2 = min(frame.shape[0], y + h + pad)
    x1 = max(0, x - pad)
    x2 = min(frame.shape[1], x + w + pad)

    region = frame[y1:y2, x1:x2]

    if region.size == 0:
        return []

    # Upscale small regions for better OCR
    if region.shape[0] < 100 or region.shape[1] < 100:
        region = cv2.resize(region, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)

    return scan_frame_for_text_codes(region)
