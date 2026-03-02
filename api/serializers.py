from rest_framework import serializers
from documents.models import Document, Field


class FieldSerializer(serializers.ModelSerializer):

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

        read_only_fields = [
            "id", "document", "key", "original_value",
            "data_type", "confidence", "corrected_at", "corrected_by",
        ]

    def get_effective_value(self, obj):

        return obj.effective_value


class DocumentListSerializer(serializers.ModelSerializer):

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

    fields = FieldSerializer(many=True, read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "form_type", "original_filename", "content_type",
            "uploaded_at", "status", "file", "fields",
        ]
