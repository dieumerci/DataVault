# Document ingestion — the main "create a document" workflow.

import logging

from django.core.files.uploadedfile import UploadedFile

from documents.models import Document, Field
from .extraction import ExtractedField, extract_text_from_pdf, parse_fields

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/acrobat",
    "applications/vnd.pdf",
    "text/pdf",
}

GENERIC_BINARY_CONTENT_TYPES = {"application/octet-stream", ""}

MAX_FILE_SIZE = 10 * 1024 * 1024


def _is_pdf_upload(file: UploadedFile) -> bool:
    content_type = (file.content_type or "").lower().strip()

    filename = (file.name or "").lower()

    if content_type in ALLOWED_CONTENT_TYPES:
        return True

    if filename.endswith(".pdf") and content_type in GENERIC_BINARY_CONTENT_TYPES:
        return True

    return False


def ingest_pdf(file: UploadedFile, form_type: str = "") -> Document:

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
    doc = Document.objects.create(
        form_type=form_type,
        original_filename=file.name or "",
        content_type=file.content_type or "application/pdf",
        status=Document.Status.UPLOADED,
        file=file,
    )

    # --- Step 3 & 4: Extract text and parse fields ---
    try:
        file.seek(0)
        raw_text = extract_text_from_pdf(file)
        found_fields = parse_fields(raw_text)
    except Exception:
        logger.exception("Extraction failed for document %s", doc.id)
        doc.status = Document.Status.ERROR
        doc.save(update_fields=["status"])
        return doc

    # --- Step 5: Store fields ---
    _bulk_create_fields(doc, found_fields)

    # --- Step 6: Set final status ---
 
    doc.status = Document.Status.PROCESSED if found_fields else Document.Status.ERROR
    doc.save(update_fields=["status"])
    return doc


def ingest_json(payload: dict) -> Document:
    
    form_type = payload.get("form_type", "")
    raw_fields = payload.get("fields", [])

    if not raw_fields:
        raise ValueError("Payload must include at least one field in 'fields'.")

    doc = Document.objects.create(
        form_type=form_type,
        original_filename="",
        content_type="application/json",
        status=Document.Status.PROCESSED,  
    )

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
