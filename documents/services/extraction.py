# PDF text extraction and field parsing.

import re
from typing import NamedTuple

from pypdf import PdfReader


class ExtractedField(NamedTuple):
    key: str
    value: str
    data_type: str
    confidence: float

def extract_text_from_pdf(file_obj) -> str:
        
    reader = PdfReader(file_obj)
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n".join(pages)


_ROUTING_RE = re.compile(r"\b(\d{9})\b")

_ACCOUNT_RE = re.compile(r"\b(\d{8,17})\b")

_AMOUNT_RE = re.compile(r"\$\s?([\d,]+\.?\d{0,2})")


_NAME_RE = re.compile(
    r"(?:name|customer|applicant|account\s*holder)[:\s]*([A-Z][a-z]+(?: [A-Z][a-z]+)+)",
    re.IGNORECASE,
)


def _find_routing_number(text: str) -> list[ExtractedField]:
    """
    
    Look for a 9-digit routing number.
    
    """
    match = _ROUTING_RE.search(text)
    if match:
        return [ExtractedField("routing_number", match.group(1), "string", 0.6)]
    return []


def _find_account_number(text: str) -> list[ExtractedField]:
    
    for match in _ACCOUNT_RE.finditer(text):
        digits = match.group(1)
        if len(digits) != 9:  # skip routing numbers
            return [ExtractedField("account_number", digits, "string", 0.5)]
    return []


def _find_amount(text: str) -> list[ExtractedField]:

    match = _AMOUNT_RE.search(text)
    if match:
        raw = match.group(1).replace(",", "")
        return [ExtractedField("amount", raw, "number", 0.7)]
    return []


def _find_customer_name(text: str) -> list[ExtractedField]:

    match = _NAME_RE.search(text)
    if match:
        return [ExtractedField("customer_name", match.group(1).strip(), "string", 0.4)]
    return []

_ALL_PARSERS = [
    _find_routing_number,
    _find_account_number,
    _find_amount,
    _find_customer_name,
]


def parse_fields(text: str) -> list[ExtractedField]:

    results = []
    for parser in _ALL_PARSERS:
        results.extend(parser(text))
    return results
