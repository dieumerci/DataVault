
import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from documents.models import Document, Field
from documents.services.ingestion import ingest_json, ingest_pdf
from documents.services.search import search_documents


def index(request):
    return redirect("ui:upload")


# ─── Upload ─────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
@login_required  # only authenticated users can upload documents
def upload(request):

    if request.method == "GET":
        return render(request, "ui/upload.html")

    error = None
    doc = None

    if request.FILES.get("file"):
        try:
            form_type = request.POST.get("form_type", "")
            doc = ingest_pdf(request.FILES["file"], form_type=form_type)
        except ValueError as e:
            error = str(e)

    elif request.POST.get("json_payload"):
        try:
            data = json.loads(request.POST["json_payload"])
            doc = ingest_json(data)
        except json.JSONDecodeError:
            error = "Invalid JSON. Please check the format and try again."
        except ValueError as e:
            error = str(e)
    else:
        error = "Please upload a PDF or paste a JSON payload."

    if doc:
        return redirect("ui:document_detail", pk=doc.pk)

    return render(request, "ui/upload.html", {"error": error})

# ─── Document Detail ────────────────────────────────────────

@require_GET
def document_detail(request, pk):
    doc = get_object_or_404(
        Document.objects.prefetch_related("fields"),
        pk=pk,
    )
    return render(request, "ui/document_detail.html", {"document": doc})

# ─── Field Correction (HTMX endpoint) ──────────────────────

@require_POST
@login_required
def correct_field(request, pk):

    field = get_object_or_404(Field, pk=pk)
    new_value = request.POST.get("corrected_value", "").strip()

    if new_value:
        # Apply the correction and stamp the audit fields
        field.corrected_value = new_value
        field.corrected_at = timezone.now()
        field.corrected_by = request.user
    else:
        field.corrected_value = None
        field.corrected_at = None
        field.corrected_by = None

    field.save(update_fields=["corrected_value", "corrected_at", "corrected_by"])

    return render(request, "ui/partials/field_row.html", {"field": field})

# ─── Search ─────────────────────────────────────────────────

@require_GET
def search(request):

    params = {
        "form_type": request.GET.get("form_type", ""),
        "field_key": request.GET.get("field_key", ""),
        "field_value": request.GET.get("field_value", ""),
        "uploaded_from": request.GET.get("uploaded_from", ""),
        "uploaded_to": request.GET.get("uploaded_to", ""),
    }

    for key in ("amount_min", "amount_max"):
        raw = request.GET.get(key)
        if raw:
            try:
                params[key] = float(raw)
            except ValueError:
                pass  

    documents = search_documents(params)

    if request.headers.get("HX-Request"):
        return render(request, "ui/partials/search_results.html", {"documents": documents})

    return render(request, "ui/search.html", {"documents": documents, "params": params})
