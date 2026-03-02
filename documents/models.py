import uuid

from django.conf import settings
from django.db import models


class Document(models.Model):

    class Status(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"      
        PROCESSED = "processed", "Processed"   
        ERROR = "error", "Error"              

  
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # What kind of form this is. Indexed because it's the #1 search filter.
    form_type = models.CharField(
        max_length=64, blank=True, default="", db_index=True,
        help_text='e.g. "w9", "ach_authorization", "loan_application"',
    )

    original_filename = models.CharField(max_length=255, blank=True, default="")
    content_type = models.CharField(max_length=128, blank=True, default="")

    uploaded_at = models.DateTimeField(auto_now_add=True, db_index=True)

    status = models.CharField(
        max_length=16, choices=Status.choices,
        default=Status.UPLOADED, db_index=True,
    )


    file = models.FileField(upload_to="documents/%Y/%m/%d/", blank=True)

    class Meta:
        ordering = ["-uploaded_at"]  # newest first by default

    def __str__(self):
        name = self.original_filename or str(self.id)[:8]
        return f"{self.form_type or 'unknown'} — {name}"


class Field(models.Model):
    # A single extracted data field from a document.

    class DataType(models.TextChoices):
        STRING = "string", "String"
        NUMBER = "number", "Number"
        DATE = "date", "Date"
    document = models.ForeignKey(
        Document, on_delete=models.CASCADE, related_name="fields",
    )

    key = models.CharField(max_length=128, db_index=True)

    original_value = models.TextField()

    corrected_value = models.TextField(null=True, blank=True)

    data_type = models.CharField(
        max_length=16, choices=DataType.choices, default=DataType.STRING,
    )

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
        
        indexes = [
            models.Index(fields=["document", "key"]),
        ]

    def __str__(self):
        return f"{self.key} = {self.effective_value}"

    @property
    def effective_value(self):

        if self.corrected_value is not None:
            return self.corrected_value
        return self.original_value
