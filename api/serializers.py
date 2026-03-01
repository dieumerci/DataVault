"""
DRF Serializers — translate between Django models and JSON.

Serializers are the bridge between our Python model objects and the JSON
that API clients consume. They handle two directions:
  - Serialization: Model → JSON (for responses)
  - Deserialization: JSON → validated data (for creating/updating)

We have three serializers, each for a specific use case:
  - FieldSerializer: full field representation including computed effective_value
  - DocumentListSerializer: lightweight (no nested fields) for list endpoints
  - DocumentDetailSerializer: full document with all fields nested

Why three instead of one?
  The list endpoint might return hundreds of documents. If we nested all
  their fields, the response would be enormous and slow. So the list view
  returns just a field_count, and the detail view (one document at a time)
  returns the full nested fields. This is a common pattern in REST APIs:
  a lightweight list serializer and a richer detail serializer.
"""

from rest_framework import serializers
from documents.models import Document, Field


class FieldSerializer(serializers.ModelSerializer):
    """
    Full representation of a single extracted field.

    The key design choice here is `effective_value` — a computed field
    that doesn't exist in the database. It returns corrected_value if
    a correction has been made, otherwise original_value. This way API
    clients always get "the right answer" without needing to implement
    the fallback logic themselves.

    Most fields are read-only because they're set during ingestion.
    The only writable field is corrected_value (via PATCH).
    """

    # SerializerMethodField is a DRF concept: it calls get_effective_value()
    # during serialization and includes the result in the JSON output.
    # It's read-only by nature since it's computed, not stored.
    effective_value = serializers.SerializerMethodField()

    class Meta:
        model = Field
        fields = [
            "id",
            "document",
            "key",
            "original_value",
            "corrected_value",
            "effective_value",   # computed — not a database column
            "data_type",
            "confidence",
            "corrected_at",
            "corrected_by",
        ]
        # Everything except corrected_value is read-only. We don't want
        # API clients changing the original_value, key, or confidence —
        # those are set once during extraction and never modified.
        read_only_fields = [
            "id", "document", "key", "original_value",
            "data_type", "confidence", "corrected_at", "corrected_by",
        ]

    def get_effective_value(self, obj):
        """
        Delegate to the model's @property to compute the effective value.
        This keeps the logic in one place (the model), not duplicated here.
        """
        return obj.effective_value


class DocumentListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer used when listing many documents.

    Instead of nesting every field (which would be expensive for 100+
    documents), we just include a field_count so the client knows how
    many fields each document has. They can fetch the full details by
    hitting the detail endpoint for a specific document.
    """

    # Another SerializerMethodField — counts the related fields without
    # including their full data in the response.
    field_count = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id", "form_type", "original_filename", "content_type",
            "uploaded_at", "status", "field_count",
        ]

    def get_field_count(self, obj):
        """Return how many fields this document has."""
        return obj.fields.count()


class DocumentDetailSerializer(serializers.ModelSerializer):
    """
    Full serializer for viewing a single document.

    Nests all fields so the client gets everything in one API call.
    This is only used for the detail endpoint (one document at a time)
    and for the create response (showing what was just created).
    """

    # Nested serializer: includes the full FieldSerializer for each
    # related field. many=True because a document has multiple fields.
    # read_only=True because fields are created during ingestion,
    # not through this serializer.
    fields = FieldSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "form_type", "original_filename", "content_type",
            "uploaded_at", "status", "file", "fields",
        ]
