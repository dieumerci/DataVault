from django.db.models import Q
from django.db.models.functions import Coalesce

from documents.models import Document, Field


def search_documents(params: dict):
    # Filter documents based on search criteria.

    qs = Document.objects.all()

    # --- Filter by form type (exact match) ---
    form_type = params.get("form_type")
    if form_type:
        qs = qs.filter(form_type=form_type)

    # --- Filter by upload date range ---
    uploaded_from = params.get("uploaded_from")
    if uploaded_from:
        qs = qs.filter(uploaded_at__gte=uploaded_from)

    uploaded_to = params.get("uploaded_to")
    if uploaded_to:
        qs = qs.filter(uploaded_at__lte=uploaded_to)

    # --- Filter by field key + value (uses COALESCE for effective value) ---
    field_key = params.get("field_key")
    field_value = params.get("field_value")
    if field_key and field_value:
        matching_doc_ids = (
            Field.objects
            .annotate(effective=Coalesce("corrected_value", "original_value"))
            .filter(key=field_key, effective__icontains=field_value)
            .values_list("document_id", flat=True)
        )
        qs = qs.filter(id__in=matching_doc_ids)

    # --- Filter by amount range ---
    amount_min = params.get("amount_min")
    amount_max = params.get("amount_max")
    if amount_min is not None or amount_max is not None:
        amount_fields = (
            Field.objects
            .filter(key="amount")
        )
        if amount_min is not None:
            amount_fields = amount_fields.extra(
                where=["CAST(COALESCE(corrected_value, original_value) AS NUMERIC) >= %s"],
                params=[amount_min],
            )
        if amount_max is not None:
            amount_fields = amount_fields.extra(
                where=["CAST(COALESCE(corrected_value, original_value) AS NUMERIC) <= %s"],
                params=[amount_max],
            )
        qs = qs.filter(id__in=amount_fields.values_list("document_id", flat=True))

    return qs.distinct()
