"""Pokemon TCG redemption code validation and normalization."""

import re
from typing import Optional

# Pokemon TCG codes are 13 alphanumeric characters
# They may appear with hyphens in various groupings:
#   XXX-XXXX-XXX-XXX  (3-4-3-3)
#   XXXX-XXXX-XXXXX   (various groupings)
#   XXXXXXXXXXXXX      (no hyphens)
# Characters: uppercase letters and digits (no lowercase, no special chars other than hyphens)

# Match a 13-character alphanumeric code with optional hyphens
# This is flexible enough to catch various groupings
CODE_WITH_HYPHENS = re.compile(
    r'\b([A-Z0-9]{2,5}[-\s][A-Z0-9]{2,5}[-\s][A-Z0-9]{2,5}(?:[-\s][A-Z0-9]{2,5})?)\b'
)

# Match exactly 13 consecutive alphanumeric chars (no hyphens)
CODE_NO_HYPHENS = re.compile(
    r'\b([A-Z0-9]{13})\b'
)

# Common OCR misreads to correct
OCR_CORRECTIONS = {
    'O': '0',  # Letter O → digit 0 (context-dependent)
    'I': '1',  # Letter I → digit 1
    'l': '1',  # Lowercase L → digit 1
    'S': '5',  # S → 5 (less common)
    'B': '8',  # B → 8 (less common)
}


def normalize_code(code: str) -> str:
    """Normalize a code by removing hyphens/spaces and uppercasing."""
    return re.sub(r'[-\s]', '', code.upper())


def validate_code(text: str) -> Optional[str]:
    """Check if text contains a valid Pokemon TCG code.

    Returns the normalized code (uppercase, no hyphens) if valid, None otherwise.
    """
    if not text:
        return None

    text_upper = text.upper().strip()

    # Try with hyphens/spaces first
    match = CODE_WITH_HYPHENS.search(text_upper)
    if match:
        normalized = normalize_code(match.group(1))
        if len(normalized) == 13 and normalized.isalnum():
            return normalized

    # Try without hyphens
    match = CODE_NO_HYPHENS.search(text_upper)
    if match:
        return match.group(1)

    return None


def extract_codes_from_text(text: str) -> list[str]:
    """Extract all potential Pokemon TCG codes from a block of text.

    Returns list of normalized codes (unique, uppercase, no hyphens).
    """
    if not text:
        return []

    text_upper = text.upper()
    found = set()

    # Find codes with hyphens/spaces
    for match in CODE_WITH_HYPHENS.finditer(text_upper):
        normalized = normalize_code(match.group(1))
        if len(normalized) == 13 and normalized.isalnum():
            found.add(normalized)

    # Find codes without hyphens
    for match in CODE_NO_HYPHENS.finditer(text_upper):
        found.add(match.group(1))

    return list(found)


def apply_ocr_corrections(text: str) -> str:
    """Apply common OCR misread corrections to improve code detection.

    This is aggressive — only use on text that looks like it could be a code.
    """
    # Don't correct if it's clearly a word
    if text.isalpha() and len(text) > 4:
        return text

    result = text.upper()
    # Only apply corrections that make sense in alphanumeric code context
    # We're conservative here — only fix obvious cases
    result = result.replace('l', '1')
    result = result.replace('|', '1')

    return result
