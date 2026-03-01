"""
Document search service.

Builds a filtered Document queryset from search parameters.
The interesting part is how we handle "effective value" — when
searching by field value, we need to match against the corrected
value if it exists, otherwise the original value.

In SQL terms: COALESCE(corrected_value, original_value)
In Django ORM: Coalesce("corrected_value", "original_value")

We use subqueries (Field -> Document IDs) instead of JOINs to
avoid the "multiplication problem" where a document with 5 fields
would appear 5 times in JOIN results.
"""

from django.db.models import Q
from django.db.models.functions import Coalesce

from documents.models import Document, Field


def search_documents(params: dict):
    """
    Filter documents based on search criteria.

    Accepts a dict of parameters (typically from request.GET):
      - form_type: exact match
      - field_key + field_value: find docs with a field whose effective value contains the search term
      - amount_min / amount_max: range filter on "amount" fields
      - uploaded_from / uploaded_to: date range on uploaded_at

    Returns a Document queryset (lazy — not executed until iterated).
    """
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

    # --- Filter by field key + value ---
    # This is the tricky one. We need to:
    # 1. Find Fields where key matches AND effective_value contains the search term
    # 2. Get the document IDs from those fields
    # 3. Filter our Document queryset by those IDs
    #
    # We use Coalesce to compute effective_value at the database level,
    # so the DB does the work, not Python.
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
    # Amount values are stored as strings (because all field values are text).
    # To do numeric comparison, we CAST to NUMERIC in raw SQL.
    # This is one of the few places where Django's ORM can't do exactly
    # what we need, so we use .extra() to inject raw SQL.
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

    # .distinct() removes duplicates that can happen when a document
    # matches multiple subquery conditions.
    return qs.distinct()
