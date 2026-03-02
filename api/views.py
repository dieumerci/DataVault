
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
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_serializer_class(self):
        if self.request.method == "GET":
            return DocumentListSerializer
        return DocumentDetailSerializer

    def get_queryset(self):
        return search_documents(self.request.query_params)

    def create(self, request, *args, **kwargs):

        uploaded_file = request.FILES.get("file")

        if uploaded_file:
            try:
                form_type = request.data.get("form_type", "")
                doc = ingest_pdf(uploaded_file, form_type=form_type)
            except ValueError as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        else:
            try:
                doc = ingest_json(request.data)
            except (ValueError, KeyError) as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        serializer = DocumentDetailSerializer(doc, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class DocumentDetailView(generics.RetrieveAPIView):
    queryset = Document.objects.prefetch_related("fields")
    serializer_class = DocumentDetailSerializer
    lookup_field = "pk"


# ─── Field Corrections ──────────────────────────────────────

class FieldCorrectionView(generics.UpdateAPIView):

    queryset = Field.objects.all()
    serializer_class = FieldSerializer
    permission_classes = [permissions.IsAuthenticated]

    http_method_names = ["patch"]

    def perform_update(self, serializer):
        serializer.save(
            corrected_at=timezone.now(),
            corrected_by=self.request.user,
        )


# ─── Reports ────────────────────────────────────────────────

class TopCorrectionsView(APIView):

    def get(self, request):
        limit = int(request.query_params.get("limit", 3))
        date_from = request.query_params.get("date_from")
        date_to = request.query_params.get("date_to")

        results = top_corrections(
            limit=limit,
            date_from=date_from,
            date_to=date_to,
        )
        return Response(results)
