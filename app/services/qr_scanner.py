"""QR code detection from video frames using pyzbar and OpenCV."""

import logging
from typing import Optional

import cv2
import numpy as np
from pyzbar import pyzbar
from pyzbar.pyzbar import ZBarSymbol

logger = logging.getLogger(__name__)


def scan_frame_for_qr(frame: np.ndarray) -> list[str]:
    """Scan a video frame for QR codes.

    Args:
        frame: BGR image as numpy array (from cv2.imread or similar)

    Returns:
        List of decoded QR code strings found in the frame.
    """
    results = set()

    # Strategy 1: Direct scan on original frame
    decoded = _decode_qr(frame)
    results.update(decoded)

    # Strategy 2: Grayscale
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    decoded = _decode_qr(gray)
    results.update(decoded)

    # Strategy 3: Enhanced contrast (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    decoded = _decode_qr(enhanced)
    results.update(decoded)

    # Strategy 4: Sharpened
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    sharpened = cv2.filter2D(gray, -1, kernel)
    decoded = _decode_qr(sharpened)
    results.update(decoded)

    # Strategy 5: Adaptive threshold
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    decoded = _decode_qr(thresh)
    results.update(decoded)

    # Strategy 6: Upscale small QR codes (2x)
    if frame.shape[0] < 1080:
        upscaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        decoded = _decode_qr(upscaled)
        results.update(decoded)

    return list(results)


def _decode_qr(image: np.ndarray) -> list[str]:
    """Run pyzbar decoder on an image, returning decoded strings."""
    try:
        decoded_objects = pyzbar.decode(image, symbols=[ZBarSymbol.QRCODE])
        results = []
        for obj in decoded_objects:
            try:
                data = obj.data.decode("utf-8").strip()
                if data:
                    results.append(data)
            except (UnicodeDecodeError, AttributeError):
                continue
        return results
    except Exception as e:
        logger.debug(f"pyzbar decode error: {e}")
        return []


def scan_frame_for_all_barcodes(frame: np.ndarray) -> list[dict]:
    """Scan for all barcode types (QR, Code128, etc.) — broader search."""
    results = []

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    for image in [frame, gray]:
        try:
            decoded_objects = pyzbar.decode(image)
            for obj in decoded_objects:
                try:
                    data = obj.data.decode("utf-8").strip()
                    if data:
                        results.append({
                            "data": data,
                            "type": obj.type,
                            "rect": {
                                "x": obj.rect.left,
                                "y": obj.rect.top,
                                "w": obj.rect.width,
                                "h": obj.rect.height,
                            },
                        })
                except (UnicodeDecodeError, AttributeError):
                    continue
        except Exception:
            continue

    return results
