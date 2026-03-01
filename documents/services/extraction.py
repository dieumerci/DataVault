"""
PDF text extraction and field parsing.

This module does two things:
  1. Pull raw text out of a PDF file (using pypdf)
  2. Scan that text for common financial fields using regex

The regex approach is intentionally simple. In production you'd use
OCR (Tesseract, AWS Textract) for scanned docs and ML models for
entity extraction. But for this take-home, regex on text-based PDFs
is the right trade-off: it's easy to understand, easy to test, and
demonstrates the full pipeline without external service dependencies.

Each parser function returns a list of tuples:
  (field_key, value, data_type, confidence_score)
"""

import re
from typing import NamedTuple

from pypdf import PdfReader


class ExtractedField(NamedTuple):
    """Lightweight container for a parsed field. NamedTuple so it's immutable and clean."""
    key: str
    value: str
    data_type: str
    confidence: float


# --- Text Extraction ---

def extract_text_from_pdf(file_obj) -> str:
    """
    Read every page of a PDF and return all the text concatenated.

    pypdf works on text-based PDFs (where text is stored as characters).
    It will NOT work on scanned documents (those are just images).
    For scanned docs you'd need OCR — noted as a trade-off in SOLUTION.md.
    """
    reader = PdfReader(file_obj)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


# --- Field Parsers ---
# Each one looks for a specific pattern in the text.
# They're separate functions so they're independently testable
# and you can add new ones without touching existing code.

# ABA routing numbers are exactly 9 digits
_ROUTING_RE = re.compile(r"\b(\d{9})\b")

# Account numbers are 8-17 digits (wider range than routing)
_ACCOUNT_RE = re.compile(r"\b(\d{8,17})\b")

# Dollar amounts like $1,234.56 or $500
_AMOUNT_RE = re.compile(r"\$\s?([\d,]+\.?\d{0,2})")

# Names following a label like "Name:", "Customer:", "Applicant:"
# Looks for two+ capitalized words after the label
_NAME_RE = re.compile(
    r"(?:name|customer|applicant|account\s*holder)[:\s]*([A-Z][a-z]+(?: [A-Z][a-z]+)+)",
    re.IGNORECASE,
)


def _find_routing_number(text: str) -> list[ExtractedField]:
    """
    Look for a 9-digit routing number.

    Confidence is 0.6 because lots of 9-digit numbers exist that
    aren't routing numbers (SSNs, zip+4 codes, etc). In production
    you'd validate the checksum digit.
    """
    match = _ROUTING_RE.search(text)
    if match:
        return [ExtractedField("routing_number", match.group(1), "string", 0.6)]
    return []


def _find_account_number(text: str) -> list[ExtractedField]:
    """
    Look for an 8-17 digit account number.

    We skip any 9-digit match to avoid double-counting routing numbers.
    Confidence is 0.5 because long digit strings are ambiguous.
    """
    for match in _ACCOUNT_RE.finditer(text):
        digits = match.group(1)
        if len(digits) != 9:  # skip routing numbers
            return [ExtractedField("account_number", digits, "string", 0.5)]
    return []


def _find_amount(text: str) -> list[ExtractedField]:
    """
    Look for dollar amounts like "$1,234.56".

    We strip commas and return just the number string.
    Confidence is 0.7 because the $ sign is a strong signal.
    """
    match = _AMOUNT_RE.search(text)
    if match:
        raw = match.group(1).replace(",", "")
        return [ExtractedField("amount", raw, "number", 0.7)]
    return []


def _find_customer_name(text: str) -> list[ExtractedField]:
    """
    Look for a labeled name like "Customer Name: Jane Smith".

    This is the weakest parser — it only works when there's an
    explicit label. Confidence is 0.4 to reflect that.
    """
    match = _NAME_RE.search(text)
    if match:
        return [ExtractedField("customer_name", match.group(1).strip(), "string", 0.4)]
    return []


# All parsers in one list. To add a new field type, just write
# a function and append it here.
_ALL_PARSERS = [
    _find_routing_number,
    _find_account_number,
    _find_amount,
    _find_customer_name,
]


def parse_fields(text: str) -> list[ExtractedField]:
    """
    Run all field parsers on the given text and collect results.

    This is the main entry point for the extraction pipeline.
    Returns a flat list of everything we found.
    """
    results = []
    for parser in _ALL_PARSERS:
        results.extend(parser(text))
    return results
