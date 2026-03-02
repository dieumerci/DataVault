# Admin configuration — mostly for convenience during development.

from django.contrib import admin
from .models import Document, Field

class FieldInline(admin.TabularInline):
    """Show fields inline on the document admin page."""
    model = Field
    extra = 0  # don't show empty rows by default
    readonly_fields = ("original_value", "confidence", "corrected_at", "corrected_by")

@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("id", "form_type", "original_filename", "status", "uploaded_at")
    list_filter = ("status", "form_type")
    search_fields = ("original_filename",)
    inlines = [FieldInline]


@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ("id", "document", "key", "original_value", "corrected_value")
    list_filter = ("key", "data_type")
