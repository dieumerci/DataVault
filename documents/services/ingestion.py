"""
Document ingestion — the main "create a document" workflow.

Two entry points:
  1. ingest_pdf()  — user uploads a PDF file
  2. ingest_json() — developer/test path with pre-extracted fields

Both return a saved Document with its Fields already in the database.

Why a separate service instead of putting this in the view?
  - The view's job is HTTP (parse request, return response)
  - This service's job is business logic (validate, extract, store)
  - We can call this from views, management commands, or Celery tasks
  - It's easier to unit test without mocking HTTP
"""

import logging

from django.core.files.uploadedfile import UploadedFile

from documents.models import Document, Field
from .extraction import ExtractedField, extract_text_from_pdf, parse_fields

logger = logging.getLogger(__name__)

# Only accept PDFs — reject Word docs, images, etc.
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/acrobat",
    "applications/vnd.pdf",
    "text/pdf",
}

# Some clients/browsers upload PDFs as generic binary streams.
GENERIC_BINARY_CONTENT_TYPES = {"application/octet-stream", ""}

# 10MB limit — matches our Django setting
MAX_FILE_SIZE = 10 * 1024 * 1024


def _is_pdf_upload(file: UploadedFile) -> bool:
    """Best-effort PDF detection using MIME type plus filename fallback."""
    content_type = (file.content_type or "").lower().strip()
    filename = (file.name or "").lower()

    if content_type in ALLOWED_CONTENT_TYPES:
        return True

    if filename.endswith(".pdf") and content_type in GENERIC_BINARY_CONTENT_TYPES:
        return True

    return False


def ingest_pdf(file: UploadedFile, form_type: str = "") -> Document:
    """
    Full PDF ingestion pipeline:
      1. Validate the file (type, size)
      2. Create a Document record
      3. Extract text from the PDF
      4. Parse fields out of the text
      5. Store the fields
      6. Update status

    If extraction fails, we still keep the file — an ops user can
    manually enter the fields later. That's why status becomes "error"
    instead of deleting the document.
    """

    # --- Step 1: Validate ---
    if not _is_pdf_upload(file):
        raise ValueError(
            "Only PDF files are accepted. Please upload a .pdf file."
        )

    if file.size and file.size > MAX_FILE_SIZE:
        raise ValueError(
            f"File too large ({file.size} bytes). Maximum is 10MB."
        )

    # --- Step 2: Create the document record ---
    # We save the file first so even if extraction fails, the PDF is preserved.
    doc = Document.objects.create(
        form_type=form_type,
        original_filename=file.name or "",
        content_type=file.content_type or "application/pdf",
        status=Document.Status.UPLOADED,
        file=file,
    )

    # --- Step 3 & 4: Extract text and parse fields ---
    try:
        # Seek back to start — Django may have partially read the file
        # during the .create() above (to save it to disk).
        file.seek(0)
        raw_text = extract_text_from_pdf(file)
        found_fields = parse_fields(raw_text)
    except Exception:
        # Log the full traceback but don't crash — the file is already saved.
        logger.exception("Extraction failed for document %s", doc.id)
        doc.status = Document.Status.ERROR
        doc.save(update_fields=["status"])
        return doc

    # --- Step 5: Store fields ---
    _bulk_create_fields(doc, found_fields)

    # --- Step 6: Set final status ---
    # "processed" if we found at least one field, "error" if we got nothing.
    # An empty extraction isn't a crash — the PDF might just not have
    # recognizable fields (e.g., a cover letter).
    doc.status = Document.Status.PROCESSED if found_fields else Document.Status.ERROR
    doc.save(update_fields=["status"])
    return doc


def ingest_json(payload: dict) -> Document:
    """
    Create a document from a JSON payload of pre-extracted fields.

    This is the "developer/test path" — useful for:
      - Integration testing without needing a real PDF
      - Clients that do their own extraction and just want to store results
      - Quick demos in the Loom walkthrough

    Expected format:
    {
        "form_type": "w9",
        "fields": [
            {"key": "routing_number", "value": "021000021", "data_type": "string", "confidence": 0.9},
            ...
        ]
    }
    """
    form_type = payload.get("form_type", "")
    raw_fields = payload.get("fields", [])

    if not raw_fields:
        raise ValueError("Payload must include at least one field in 'fields'.")

    doc = Document.objects.create(
        form_type=form_type,
        original_filename="",
        content_type="application/json",
        status=Document.Status.PROCESSED,  # JSON fields are "pre-extracted"
    )

    # Convert the JSON dicts into our ExtractedField namedtuple format
    # so we can reuse the same _bulk_create_fields helper.
    extracted = [
        ExtractedField(
            key=f["key"],
            value=str(f.get("value", "")),
            data_type=f.get("data_type", "string"),
            confidence=f.get("confidence", 1.0),
        )
        for f in raw_fields
    ]
    _bulk_create_fields(doc, extracted)
    return doc


def _bulk_create_fields(doc: Document, fields: list[ExtractedField]) -> None:
    """
    Save a batch of extracted fields to the database in one query.

    bulk_create is much faster than creating them one by one because
    it sends a single INSERT with multiple rows instead of N separate INSERTs.
    """
    Field.objects.bulk_create([
        Field(
            document=doc,
            key=f.key,
            original_value=f.value,
            data_type=f.data_type,
            confidence=f.confidence,
        )
        for f in fields
    ])
