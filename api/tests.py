"""
API integration tests.

These test the HTTP layer end-to-end — they make real requests to real
endpoints with a real test database. We focus on the scenarios that
would cause the most damage if they broke:

  1. Auth enforcement — can't modify financial data without logging in
  2. Reporting endpoint — tests the raw SQL query from ingestion to response
  3. Search with corrections — verifies COALESCE logic at the database level

Why these three?
  Auth is a hard requirement. If unauthenticated users could PATCH field
  values, the whole correction audit trail falls apart.

  The reporting query uses raw SQL, which is more error-prone than ORM
  queries. A typo in the SQL would only surface at runtime.

  Search with corrections is the most subtle: we need to prove that
  searching for "Jane" finds a field that was *corrected* to "Jane",
  and searching for the *original* value doesn't find it anymore.
  If this breaks, ops users would see stale data.
"""

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from documents.models import Document, Field


class AuthTests(TestCase):
    """
    Verify that write endpoints require authentication.

    This is critical for a financial document system — we can't let
    anonymous users modify extracted field values.
    """

    def setUp(self):
        # Create a document with one field to test corrections against
        self.client = APIClient()
        self.doc = Document.objects.create(form_type="w9", status="processed")
        self.field = Field.objects.create(
            document=self.doc, key="amount", original_value="100.00",
        )

    def test_anonymous_patch_is_rejected(self):
        """
        Sending a PATCH without any authentication should fail.
        DRF returns either 401 (no credentials) or 403 (insufficient
        permissions) depending on the auth backend — both are correct.
        """
        resp = self.client.patch(
            f"/api/fields/{self.field.pk}/",
            {"corrected_value": "200.00"},
            format="json",
        )
        self.assertIn(resp.status_code, [401, 403])

    def test_authenticated_patch_works(self):
        """
        An authenticated user should be able to correct a field.
        We also verify the audit fields are stamped correctly:
          - corrected_value is saved
          - corrected_by points to the user who made the change
          - corrected_at is set (not None)
        """
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
    """
    Test the top-corrections reporting endpoint end-to-end.

    This endpoint hits our raw SQL query, so it's important to verify
    that the GROUP BY, COUNT, and ORDER BY all work correctly together.
    A bug here would give ops teams wrong data about which fields need
    the most attention.
    """

    def setUp(self):
        self.client = APIClient()
        self.doc = Document.objects.create(form_type="w9", status="processed")
        now = timezone.now()

        # Set up a known distribution of corrections:
        #   "amount"         → 5 corrections (should rank #1)
        #   "routing_number" → 3 corrections (should rank #2)
        #   "customer_name"  → 1 correction  (should rank #3)
        #   "account_number" → 0 corrections (should NOT appear)
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
        # This field has NO correction — it should be excluded from results
        Field.objects.create(
            document=self.doc, key="account_number",
            original_value="12345",
        )

    def test_returns_top_3_in_order(self):
        """
        The report should return the three most-corrected field keys,
        ordered by correction count descending.
        """
        resp = self.client.get("/api/reports/top-corrections/")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(len(data), 3)
        self.assertEqual(data[0]["key"], "amount")
        self.assertEqual(data[0]["correction_count"], 5)
        self.assertEqual(data[1]["key"], "routing_number")
        self.assertEqual(data[2]["key"], "customer_name")


class SearchWithCorrectionsTests(TestCase):
    """
    The most important test in the suite: search must use effective_value.

    Scenario: a field was extracted as "John Smith" but an ops user
    corrected it to "Jane Doe". Searching for "Jane" should find the
    document, and searching for "John" should NOT.

    If this breaks, users would see stale data — they'd correct a field
    but search would still return results based on the old value.
    """

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
        """
        Searching for 'John' should NOT find the document anymore.
        The effective value is now 'Jane Doe', so the original 'John Smith'
        should be invisible to search. This proves COALESCE works at the DB level.
        """
        resp = self.client.get(
            "/api/documents/",
            {"field_key": "customer_name", "field_value": "John"},
        )
        self.assertEqual(resp.json()["count"], 0)
