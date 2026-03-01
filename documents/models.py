"""
Data models for the document intake system.

There are two models:
  - Document: represents an uploaded file (PDF) or a JSON submission
  - Field: a single key-value pair extracted from a document

The big idea here is "effective value". When an operations user corrects
a field, we don't overwrite the original — we store the correction
separately. Then anywhere we need "the real value", we use:

    effective_value = corrected_value if it exists, else original_value

This is the same as SQL's COALESCE(corrected_value, original_value).
It lets us always show both values for audit purposes while using
the "right" one for search and display.
"""

import uuid

from django.conf import settings
from django.db import models


class Document(models.Model):
    """
    A single uploaded document.

    Could be a W-9, ACH authorization, loan application, etc.
    The actual file is stored on disk via FileField; metadata lives here.
    """

    # We use a TextChoices enum instead of raw strings so Django
    # validates the value and gives us get_status_display() for free.
    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"      # file received, not yet processed
        PROCESSED = "processed", "Processed"   # extraction ran and found fields
        ERROR = "error", "Error"               # extraction ran but found nothing / failed

    # UUID primary key instead of auto-incrementing int.
    # Why? It's standard practice for document systems because:
    # 1. IDs are non-guessable (can't enumerate /documents/1, /documents/2...)
    # 2. IDs can be generated client-side before hitting the DB
    # 3. IDs are globally unique across databases/services
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # What kind of form this is. Indexed because it's the #1 search filter.
    form_type = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        help_text='e.g. "w9", "ach_authorization", "loan_application"',
    )

    original_filename = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=128, blank=True, default="")

    # auto_now_add=True sets this once on creation and never changes it.
    # Indexed because we filter by date range in search.
    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    status = models.CharField(
        max_length=16, choices=Status.choices,
        default=Status.UPLOADED, db_index=True,
    )

    # The actual PDF file. upload_to organizes files by date so we don't
    # end up with 10,000 files in one directory.
    # blank=True because JSON-submitted documents don't have a file.
    file = models.FileField(upload_to="documents/%Y/%m/%d/", blank=True)

    class Meta:
        ordering = ["-uploaded_at"]  # newest first by default

    def __str__(self):
        name = self.original_filename or str(self.id)[:8]
        return f"{self.form_type or 'unknown'} — {name}"


class Field(models.Model):
    """
    A single extracted data field from a document.

    Think of it as one row in a form: "routing_number" = "021000021".

    The correction workflow:
      1. PDF gets uploaded, extraction finds routing_number = "021000021"
      2. Ops user notices it's wrong, sets corrected_value = "021000089"
      3. We keep BOTH values — original for audit, corrected for downstream use
      4. effective_value always returns the "right" one
    """

    class DataType(models.TextChoices):
        STRING = "string", "String"
        NUMBER = "number", "Number"
        DATE = "date", "Date"

    # CASCADE means: if the document is deleted, delete its fields too.
    # That's the right behavior — orphaned fields make no sense.
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="fields",
    )

    # What this field represents — "routing_number", "amount", "customer_name", etc.
    key = models.CharField(max_length=128, db_index=True)

    # The value that came out of extraction. Never modified after creation.
    original_value = models.TextField()

    # Set by a human when they correct the extraction. NULL means "no correction needed".
    corrected_value = models.TextField(null=True, blank=True)

    data_type = models.CharField(
        max_length=16, choices=DataType.choices, default=DataType.STRING,
    )

    # How confident the extraction was. 0.0 = total guess, 1.0 = certain.
    # NULL for manually-entered fields (JSON upload path).
    confidence = models.FloatField(null=True, blank=True)

    # When and who made the correction — important for audit trails.
    corrected_at = models.DateTimeField(null=True, blank=True)
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True, on_delete=models.SET_NULL,
        related_name="corrections",
    )

    class Meta:
        ordering = ["key"]
        # Composite index: speeds up "find all fields for document X with key Y"
        # which is exactly the query pattern our search service uses.
        indexes = [
            models.Index(fields=["document", "key"]),
        ]

    def __str__(self):
        return f"{self.key} = {self.effective_value}"

    @property
    def effective_value(self):
        """
        The value that should be used everywhere downstream.

        If a human corrected this field, use their correction.
        Otherwise, use what came out of extraction.

        This is the Python-side equivalent of SQL's
        COALESCE(corrected_value, original_value).
        """
        if self.corrected_value is not None:
            return self.corrected_value
        return self.original_value
