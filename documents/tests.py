from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from documents.models import Document, Field
from documents.services.extraction import parse_fields
from documents.services.ingestion import ingest_json, ingest_pdf


class EffectiveValueTests(TestCase):

    def setUp(self):
        self.doc = Document.objects.create(form_type="w9", status="processed")

    def test_returns_original_when_no_correction(self):
        field = Field.objects.create(
            document=self.doc, key="amount", original_value="100.00",
        )
        self.assertEqual(field.effective_value, "100.00")

    def test_returns_corrected_when_set(self):
        field = Field.objects.create(
            document=self.doc, key="amount",
            original_value="100.00", corrected_value="200.00",
        )
        self.assertEqual(field.effective_value, "200.00")

    def test_returns_original_when_correction_is_none(self):
        field = Field.objects.create(
            document=self.doc, key="amount",
            original_value="100.00", corrected_value=None,
        )
        self.assertEqual(field.effective_value, "100.00")


class ExtractionTests(TestCase):

    def test_finds_routing_number(self):
        text = "Routing: 021000021 some other text"
        fields = parse_fields(text)
        keys = {f.key for f in fields}
        self.assertIn("routing_number", keys)

        routing = next(f for f in fields if f.key == "routing_number")
        self.assertEqual(routing.value, "021000021")

    def test_finds_dollar_amount(self):
        text = "Total due: R1,234.56 please remit"
        fields = parse_fields(text)
        amount = next(f for f in fields if f.key == "amount")
        # Commas should be stripped — we store just the number
        self.assertEqual(amount.value, "1234.56")

    def test_finds_customer_name(self):
        text = "Customer Name: Jane Doe\nAddress: 123 Main St"
        fields = parse_fields(text)
        name = next(f for f in fields if f.key == "customer_name")
        self.assertEqual(name.value, "Jane Doe")

    def test_empty_text_returns_nothing(self):
        fields = parse_fields("")
        self.assertEqual(len(fields), 0)


class JsonIngestionTests(TestCase):

    def test_creates_document_and_fields(self):
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
        with self.assertRaises(ValueError):
            ingest_json({"form_type": "w9", "fields": []})


class PdfIngestionValidationTests(TestCase):

    @patch("documents.services.ingestion.parse_fields", return_value=[])
    @patch("documents.services.ingestion.extract_text_from_pdf", return_value="dummy")
    def test_accepts_octet_stream_pdf_by_extension(self, *_):

        upload = SimpleUploadedFile(
            name="bank-statement.pdf",
            content=b"%PDF-1.4\n",
            content_type="application/octet-stream",
        )
        doc = ingest_pdf(upload, form_type="other")
        self.assertEqual(doc.original_filename, "bank-statement.pdf")

    def test_rejects_non_pdf_upload(self):

        upload = SimpleUploadedFile(
            name="bank-statement.txt",
            content=b"not a pdf",
            content_type="text/plain",
        )
        with self.assertRaises(ValueError):
            ingest_pdf(upload, form_type="other")
