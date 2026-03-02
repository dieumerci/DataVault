from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import Document, Field


class AuthTests(TestCase):

    def setUp(self):
        # Create a document with one field to test corrections against
        self.client = APIClient()
        self.doc = Document.objects.create(form_type="w9", status="processed")
        self.field = Field.objects.create(
            document=self.doc, key="amount", original_value="100.00",
        )

    def test_anonymous_patch_is_rejected(self):

        resp = self.client.patch(
            f"/api/fields/{self.field.pk}/",
            {"corrected_value": "200.00"},
            format="json",
        )
        self.assertIn(resp.status_code, [401, 403])

    def test_authenticated_patch_works(self):

        user = User.objects.create_user("tester", password="pass123")
        self.client.force_authenticate(user=user)

        resp = self.client.patch(
            f"/api/fields/{self.field.pk}/",
            {"corrected_value": "200.00"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)

        # Reload from database and verify everything was saved
        self.field.refresh_from_db()
        self.assertEqual(self.field.corrected_value, "200.00")
        self.assertEqual(self.field.corrected_by, user)
        self.assertIsNotNone(self.field.corrected_at)


class ReportingTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.doc = Document.objects.create(form_type="w9", status="processed")
        now = timezone.now()

        for i in range(5):
            Field.objects.create(
                document=self.doc, key="amount",
                original_value=str(100 + i), corrected_value=str(200 + i),
                corrected_at=now,
            )
        for i in range(3):
            Field.objects.create(
                document=self.doc, key="routing_number",
                original_value="000000000", corrected_value="111111111",
                corrected_at=now,
            )
        Field.objects.create(
            document=self.doc, key="customer_name",
            original_value="Old Name", corrected_value="New Name",
            corrected_at=now,
        )
        Field.objects.create(
            document=self.doc, key="account_number",
            original_value="12345",
        )

    def test_returns_top_3_in_order(self):

        resp = self.client.get("/api/reports/top-corrections/")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["key"], "amount")
        self.assertEqual(data[0]["correction_count"], 5)
        self.assertEqual(data[1]["key"], "routing_number")
        self.assertEqual(data[2]["key"], "customer_name")


class SearchWithCorrectionsTests(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.doc = Document.objects.create(form_type="w9", status="processed")
        # Original: "John Smith" → Corrected to: "Jane Doe"
        Field.objects.create(
            document=self.doc, key="customer_name",
            original_value="John Smith", corrected_value="Jane Doe",
        )

    def test_search_finds_corrected_value(self):
        """Searching for 'Jane' should find the document (the corrected name)."""
        resp = self.client.get(
            "/api/documents/",
            {"field_key": "customer_name", "field_value": "Jane"},
        )
        self.assertEqual(resp.json()["count"], 1)

    def test_search_ignores_stale_original(self):

        resp = self.client.get(
            "/api/documents/",
            {"field_key": "customer_name", "field_value": "John"},
        )
        self.assertEqual(resp.json()["count"], 0)
