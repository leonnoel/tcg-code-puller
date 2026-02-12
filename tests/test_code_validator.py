"""Tests for Pokemon TCG code validator."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.code_validator import validate_code, extract_codes_from_text, normalize_code


def test_valid_13_char_code():
    """13 uppercase alphanumeric chars should be valid."""
    assert validate_code("ABC1234DEF567") == "ABC1234DEF567"


def test_valid_code_with_hyphens():
    """Code with hyphens in 3-4-3-3 grouping."""
    assert validate_code("ABC-1234-DEF-567") == "ABC1234DEF567"


def test_valid_code_with_spaces():
    """Code with spaces instead of hyphens."""
    assert validate_code("ABC 1234 DEF 567") == "ABC1234DEF567"


def test_lowercase_normalized():
    """Lowercase codes should be uppercased."""
    assert validate_code("abc1234def567") == "ABC1234DEF567"


def test_invalid_too_short():
    """Too-short string should not match."""
    assert validate_code("ABC123") is None


def test_invalid_too_long():
    """Too-long string should not match."""
    assert validate_code("ABCDEFGHIJKLMNOP") is None


def test_invalid_special_chars():
    """Strings with special characters should not match."""
    assert validate_code("ABC!@#$DEF567") is None


def test_empty_string():
    assert validate_code("") is None
    assert validate_code(None) is None


def test_extract_multiple_codes():
    """Should extract multiple codes from a block of text."""
    text = """
    Here are some codes:
    ABC-1234-DEF-567
    Some text in between
    XYZ9876GHI321
    """
    codes = extract_codes_from_text(text)
    assert "ABC1234DEF567" in codes
    assert "XYZ9876GHI321" in codes
    assert len(codes) == 2


def test_extract_no_codes():
    """Should return empty list when no codes found."""
    assert extract_codes_from_text("Hello world, no codes here") == []
    assert extract_codes_from_text("") == []


def test_normalize_code():
    assert normalize_code("abc-1234-def-567") == "ABC1234DEF567"
    assert normalize_code("ABC 1234 DEF 567") == "ABC1234DEF567"


def test_code_embedded_in_text():
    """Should find a code embedded in a larger text."""
    result = validate_code("The code is ABC1234DEF567 enjoy!")
    assert result == "ABC1234DEF567"


def test_code_with_different_hyphen_groupings():
    """Various hyphen groupings should work."""
    assert validate_code("ABCD-EFGH-IJKLM") == "ABCDEFGHIJKLM"
    assert validate_code("AB-CDEF-GHI-JKLM") == "ABCDEFGHIJKLM"


if __name__ == "__main__":
    # Run all test functions
    passed = 0
    failed = 0
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            try:
                func()
                print(f"  ✅ {name}")
                passed += 1
            except AssertionError as e:
                print(f"  ❌ {name}: {e}")
                failed += 1
            except Exception as e:
                print(f"  ❌ {name}: {type(e).__name__}: {e}")
                failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
