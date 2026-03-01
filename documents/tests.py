"""
Tests for the documents domain layer.

These are unit-level tests — they test models and services directly
without touching the HTTP layer. No views, no requests, no serializers.

We focus on the things that would break the most if they regressed:
  - effective_value: the foundation of the correction system
  - extraction: regex parsers are inherently brittle, so we lock them down
  - JSON ingestion: the developer/test entry point
  - PDF validation: browsers send weird MIME types, we need to handle them

If effective_value breaks, both the UI display and search are wrong.
If extraction breaks, we stop finding fields in uploaded documents.
These are high-value tests — they protect the core of the system.
"""

from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from documents.models import Document, Field
from documents.services.extraction import parse_fields
from documents.services.ingestion import ingest_json, ingest_pdf


class EffectiveValueTests(TestCase):
    """
    Test the effective_value property on the Field model.

    This property is the foundation of the entire correction system.
    It implements the rule: "use corrected_value if it exists,
    otherwise fall back to original_value." If this breaks,
    both the UI and search display wrong data.

    We test all three possible states:
      1. No correction (corrected_value is None) → use original
      2. Correction exists → use corrected
      3. Correction explicitly set to None → use original (not None)
    """

    def setUp(self):
        # Every field needs a parent document
        self.doc = Document.objects.create(form_type="w9", status="processed")

    def test_returns_original_when_no_correction(self):
        """When no one has corrected this field, effective = original."""
        field = Field.objects.create(
            document=self.doc, key="amount", original_value="100.00",
        )
        self.assertEqual(field.effective_value, "100.00")

    def test_returns_corrected_when_set(self):
        """When a correction exists, effective = corrected (not original)."""
        field = Field.objects.create(
            document=self.doc, key="amount",
            original_value="100.00", corrected_value="200.00",
        )
        self.assertEqual(field.effective_value, "200.00")

    def test_returns_original_when_correction_is_none(self):
        """
        When corrected_value is explicitly None (not just empty string),
        effective should return original, not None. This is the COALESCE
        behavior — None means "no correction", not "corrected to nothing".
        """
        field = Field.objects.create(
            document=self.doc, key="amount",
            original_value="100.00", corrected_value=None,
        )
        self.assertEqual(field.effective_value, "100.00")


class ExtractionTests(TestCase):
    """
    Test the regex field parsers against known text patterns.

    Regex is inherently fragile — small changes to input format can
    break matches. These tests lock in the exact patterns we expect
    so we'll know immediately if a parser stops working.
    """

    def test_finds_routing_number(self):
        """A 9-digit number should be extracted as a routing number."""
        text = "Routing: 021000021 some other text"
        fields = parse_fields(text)
        keys = {f.key for f in fields}
        self.assertIn("routing_number", keys)

        routing = next(f for f in fields if f.key == "routing_number")
        self.assertEqual(routing.value, "021000021")

    def test_finds_dollar_amount(self):
        """Dollar amounts like '$1,234.56' should be found and cleaned up."""
        text = "Total due: $1,234.56 please remit"
        fields = parse_fields(text)
        amount = next(f for f in fields if f.key == "amount")
        # Commas should be stripped — we store just the number
        self.assertEqual(amount.value, "1234.56")

    def test_finds_customer_name(self):
        """A labeled name like 'Customer Name: Jane Doe' should be extracted."""
        text = "Customer Name: Jane Doe\nAddress: 123 Main St"
        fields = parse_fields(text)
        name = next(f for f in fields if f.key == "customer_name")
        self.assertEqual(name.value, "Jane Doe")

    def test_empty_text_returns_nothing(self):
        """Empty input should return an empty list, not crash."""
        fields = parse_fields("")
        self.assertEqual(len(fields), 0)


class JsonIngestionTests(TestCase):
    """
    Test the JSON ingestion path — the developer/demo shortcut.

    This path lets you create documents with known fields without
    needing a real PDF. It's also what we use in the video walkthrough
    to demo the app quickly.
    """

    def test_creates_document_and_fields(self):
        """A valid JSON payload should create a document with all its fields."""
        data = {
            "form_type": "ach_authorization",
            "fields": [
                {"key": "routing_number", "value": "021000021"},
                {"key": "amount", "value": "500.00", "data_type": "number"},
            ],
        }
        doc = ingest_json(data)

        # Check the document was created correctly
        self.assertEqual(doc.form_type, "ach_authorization")
        self.assertEqual(doc.status, "processed")
        self.assertEqual(doc.fields.count(), 2)

    def test_rejects_empty_fields_list(self):
        """
        A document with zero fields is invalid — every document should
        have at least one field to be meaningful. This prevents creating
        empty "shell" documents that add noise to search results.
        """
        with self.assertRaises(ValueError):
            ingest_json({"form_type": "w9", "fields": []})


class PdfIngestionValidationTests(TestCase):
    """
    Test PDF upload validation — especially browser MIME type quirks.

    Different browsers send different MIME types for the same PDF file:
      - Chrome/Firefox: application/pdf
      - Some older browsers: application/octet-stream (generic binary)
      - Edge (sometimes): application/x-pdf

    We need to accept all of these while still rejecting non-PDF files
    like .txt, .docx, or .jpg. The fallback is checking the file extension
    when the MIME type is ambiguous (octet-stream).
    """

    @patch("documents.services.ingestion.parse_fields", return_value=[])
    @patch("documents.services.ingestion.extract_text_from_pdf", return_value="dummy")
    def test_accepts_octet_stream_pdf_by_extension(self, *_):
        """
        A file with MIME type 'application/octet-stream' but a .pdf
        extension should still be accepted. This happens in some browsers.
        We mock the extraction functions since we're only testing validation.
        """
        upload = SimpleUploadedFile(
            name="bank-statement.pdf",
            content=b"%PDF-1.4\n",
            content_type="application/octet-stream",
        )
        doc = ingest_pdf(upload, form_type="other")
        self.assertEqual(doc.original_filename, "bank-statement.pdf")

    def test_rejects_non_pdf_upload(self):
        """
        A .txt file should be rejected outright — we only process PDFs.
        This prevents users from accidentally uploading the wrong file type.
        """
        upload = SimpleUploadedFile(
            name="bank-statement.txt",
            content=b"not a pdf",
            content_type="text/plain",
        )
        with self.assertRaises(ValueError):
            ingest_pdf(upload, form_type="other")
