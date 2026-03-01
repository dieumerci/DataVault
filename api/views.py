"""
API Views — thin HTTP wrappers around our service layer.

The pattern here is simple and deliberate: each view does exactly three things:
  1. Parse the incoming request (DRF handles most of this for us)
  2. Call the appropriate service function (the real work)
  3. Return a serialized JSON response

Why thin views? Because business logic shouldn't live in the HTTP layer.
If we ever need to ingest documents from a Celery task or a management
command, those code paths can call the same service functions without
importing anything from the API layer. This separation is the whole
point of the services/ package in the documents app.

Auth approach:
  We set DEFAULT_PERMISSION_CLASSES = [IsAuthenticatedOrReadOnly] globally
  in settings.py. That means every GET request is public (anyone can browse),
  but POST/PATCH/PUT/DELETE require a logged-in user. For the field correction
  endpoint we add an explicit IsAuthenticated check as well — belt and suspenders.
"""

from django.utils import timezone
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from documents.models import Document, Field
from documents.services.ingestion import ingest_json, ingest_pdf
from documents.services.reporting import top_corrections
from documents.services.search import search_documents

from .serializers import (
    DocumentDetailSerializer,
    DocumentListSerializer,
    FieldSerializer,
)


# ─── Documents ───────────────────────────────────────────────

class DocumentListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/documents/  — List all documents (supports search filters)
    POST /api/documents/  — Create a new document (PDF upload or JSON payload)

    The GET side delegates filtering to our search service. Any query
    parameters (form_type, field_key, amount_min, etc.) are passed
    straight through, and the service builds the appropriate queryset.

    The POST side is a "smart dispatch" — it inspects the incoming request
    to figure out which ingestion path to use. If there's a file attached,
    it's a PDF upload. If the body is JSON, it's the developer/test path.
    The view itself doesn't do any extraction or validation — that's all
    handled inside the service functions.
    """

    # We accept three content types:
    #   - MultiPart: for PDF file uploads (multipart/form-data)
    #   - FormParser: for regular HTML form submissions
    #   - JSONParser: for the JSON ingestion path (application/json)
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        # Use the lightweight serializer for list views (no nested fields —
        # just a count). Use the full serializer for create responses so the
        # client can see everything that was just created.
        if self.request.method == "GET":
            return DocumentListSerializer
        return DocumentDetailSerializer

    def get_queryset(self):
        # Instead of returning Document.objects.all(), we pass the query
        # params to our search service. If no filters are provided, it
        # returns all documents anyway — so this works for both filtered
        # and unfiltered list views.
        return search_documents(self.request.query_params)

    def create(self, request, *args, **kwargs):
        """
        Smart dispatch: decide which ingestion path to use based on
        what the client sent us.

        - File in request.FILES? → PDF upload path (ingest_pdf)
        - JSON body? → JSON payload path (ingest_json)

        Both paths return a Document instance, which we serialize
        and return as 201 Created.
        """
        uploaded_file = request.FILES.get("file")

        if uploaded_file:
            # PDF upload path — validate the file and extract fields
            try:
                form_type = request.data.get("form_type", "")
                doc = ingest_pdf(uploaded_file, form_type=form_type)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            # JSON payload path — create document from pre-extracted fields
            try:
                doc = ingest_json(request.data)
            except (ValueError, KeyError) as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = DocumentDetailSerializer(doc, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentDetailView(generics.RetrieveAPIView):
    """
    GET /api/documents/{id}/ — Retrieve a single document with all its fields.

    We use prefetch_related("fields") to load all fields in one extra query
    upfront, instead of hitting the database once per field during serialization.
    This is called "eager loading" and prevents the N+1 query problem.

    Without it: 1 query for the document + N queries for N fields.
    With it: 1 query for the document + 1 query for all fields.
    """

    queryset = Document.objects.prefetch_related("fields")
    serializer_class = DocumentDetailSerializer
    lookup_field = "pk"


# ─── Field Corrections ──────────────────────────────────────

class FieldCorrectionView(generics.UpdateAPIView):
    """
    PATCH /api/fields/{id}/ — Correct a field's value.

    This is the core data-modification endpoint. The client sends:
        {"corrected_value": "the correct value"}

    And we:
      1. Save the corrected_value (the original stays untouched)
      2. Auto-stamp corrected_at with the current time
      3. Auto-stamp corrected_by with the authenticated user

    Why PATCH-only (no PUT)?
      We only want partial updates. The client sends just corrected_value,
      and we handle the rest server-side. PUT would imply replacing the
      entire Field record, which doesn't make sense for corrections.

    Why explicit IsAuthenticated?
      The global default (IsAuthenticatedOrReadOnly) would also block
      unauthenticated PATCH requests. But corrections modify financial
      data, so we add an explicit check too — defense in depth.
    """

    queryset = Field.objects.all()
    serializer_class = FieldSerializer
    permission_classes = [permissions.IsAuthenticated]

    # Block PUT requests — only allow PATCH (partial updates)
    http_method_names = ["patch"]

    def perform_update(self, serializer):
        # DRF calls this method after validation succeeds. We use it
        # to inject the audit fields that the client shouldn't set:
        #   - corrected_at: when the correction was made
        #   - corrected_by: who made it (from the auth token/session)
        serializer.save(
            corrected_at=timezone.now(),
            corrected_by=self.request.user,
        )


# ─── Reports ────────────────────────────────────────────────

class TopCorrectionsView(APIView):
    """
    GET /api/reports/top-corrections/

    Returns the top N most frequently corrected field keys. This tells
    you which fields your extraction pipeline gets wrong most often —
    a useful signal for improving the parsers.

    This is the "non-trivial SQL" endpoint that the assignment asks for.
    The actual query lives in documents/services/reporting.py.

    Optional query params:
      - limit: how many results (default 3)
      - date_from: start date filter (ISO format)
      - date_to: end date filter (ISO format)
    """

    def get(self, request):
        # Pull optional filters from query params
        limit = int(request.query_params.get("limit", 3))
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        # Delegate to the reporting service — the view doesn't touch SQL
        results = top_corrections(
            limit=limit,
            date_from=date_from,
            date_to=date_to,
        )
        return Response(results)
