"""
UI Views — server-rendered HTML pages with HTMX for interactivity.

These views return full HTML pages for normal browser requests and
HTML fragments for HTMX requests (partial page updates without reload).

The pattern is the same everywhere:
  - Normal request   → render the full page (base template + content)
  - HTMX request     → render just the fragment that changed

HTMX tells us it's an HTMX request by sending the "HX-Request: true"
header. We check for this with request.headers.get("HX-Request").

Why HTMX instead of React/Vue?
  HTMX lets us build dynamic pages by adding HTML attributes instead
  of writing JavaScript. The server returns HTML fragments, not JSON.
  This means we get server-side rendering, Django template reuse, and
  zero JavaScript build tooling. For a CRUD app like this, it's the
  right trade-off — we get 90% of SPA interactivity with 10% of the
  complexity.

Every view here follows the "thin view" pattern: parse the request,
call a service function, render a template. No business logic in views.
"""

import json

from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from documents.models import Document, Field
from documents.services.ingestion import ingest_json, ingest_pdf
from documents.services.search import search_documents


def index(request):
    """
    Home page — just redirect to the upload page.

    We could show a dashboard here eventually, but for now the upload
    page is the natural starting point for the user flow.
    """
    return redirect("ui:upload")


# ─── Upload ─────────────────────────────────────────────────

@require_http_methods(["GET", "POST"])
@login_required  # only authenticated users can upload documents
def upload(request):
    """
    Upload page with two forms: PDF file upload and JSON textarea.

    On GET: show the empty upload forms.
    On POST: process whichever form was submitted, then redirect to
             the new document's detail page on success.

    Why two forms?
      The PDF form is the real-world path — ops users upload actual documents.
      The JSON form is the developer/demo path — lets you quickly create
      a document with known fields without needing a real PDF. It's also
      what we use in the Loom walkthrough video.

    Error handling:
      If anything goes wrong (invalid file, bad JSON, empty fields),
      we re-render the upload page with an error message instead of
      showing a generic 500 error. Much better user experience.
    """
    if request.method == "GET":
        return render(request, "ui/upload.html")

    error = None
    doc = None

    # Figure out which form was submitted by checking what's in the request
    if request.FILES.get("file"):
        # PDF upload — the file is in request.FILES
        try:
            form_type = request.POST.get("form_type", "")
            doc = ingest_pdf(request.FILES["file"], form_type=form_type)
        except ValueError as e:
            error = str(e)

    elif request.POST.get("json_payload"):
        # JSON textarea — the payload is in request.POST as a string
        try:
            data = json.loads(request.POST["json_payload"])
            doc = ingest_json(data)
        except json.JSONDecodeError:
            error = "Invalid JSON. Please check the format and try again."
        except ValueError as e:
            error = str(e)
    else:
        error = "Please upload a PDF or paste a JSON payload."

    # If we successfully created a document, redirect to its detail page
    if doc:
        return redirect("ui:document_detail", pk=doc.pk)

    # If something went wrong, re-render the upload page with the error
    return render(request, "ui/upload.html", {"error": error})


# ─── Document Detail ────────────────────────────────────────

@require_GET
def document_detail(request, pk):
    """
    Document detail page — shows all extracted fields with inline editing.

    Each field row has an HTMX-powered correction form. When the user
    saves a correction, HTMX sends a POST to correct_field() below,
    which returns just the updated row. The page never fully reloads.

    We use prefetch_related("fields") to load all fields in a single
    extra query. Without it, the template loop would fire a separate
    query for each field — the classic N+1 problem.

    The pk is a UUID (from the Document model), not an integer.
    Django handles the UUID parsing automatically via the URL pattern.
    """
    doc = get_object_or_404(
        Document.objects.prefetch_related("fields"),
        pk=pk,
    )
    return render(request, "ui/document_detail.html", {"document": doc})


# ─── Field Correction (HTMX endpoint) ──────────────────────

@require_POST
@login_required
def correct_field(request, pk):
    """
    HTMX endpoint: correct a single field and return the updated table row.

    This is the heart of the HTMX interaction. Here's the full flow:

      1. User types a correction in the inline input on the detail page
      2. User clicks "Save"
      3. HTMX intercepts the form submit and sends a POST to this endpoint
      4. We update the field in the database (corrected_value + audit fields)
      5. We render JUST the updated <tr> element (field_row.html partial)
      6. HTMX swaps the old <tr> with the new one (outerHTML swap)

    The magic is in the template attributes:
      - hx-post="{{ url }}" → sends the POST here
      - hx-target="#field-{{ id }}" → tells HTMX which element to replace
      - hx-swap="outerHTML" → replaces the entire <tr>, not just its children

    If the input is empty, we clear the correction (revert to original).
    This lets users undo a correction by submitting an empty value.
    """
    field = get_object_or_404(Field, pk=pk)
    new_value = request.POST.get("corrected_value", "").strip()

    if new_value:
        # Apply the correction and stamp the audit fields
        field.corrected_value = new_value
        field.corrected_at = timezone.now()
        field.corrected_by = request.user
    else:
        # Empty input means "undo the correction" — revert to the original
        field.corrected_value = None
        field.corrected_at = None
        field.corrected_by = None

    # Only update the fields we changed — don't touch anything else
    field.save(update_fields=["corrected_value", "corrected_at", "corrected_by"])

    # Return just the row fragment — HTMX will swap it into the table.
    # This is the same template used during the initial page render,
    # so the updated row always looks identical. One template, two uses.
    return render(request, "ui/partials/field_row.html", {"field": field})


# ─── Search ─────────────────────────────────────────────────

@require_GET
def search(request):
    """
    Search page with filters and dynamic results.

    This view serves two roles:
      1. Full page load: render the complete search page with initial results
      2. HTMX partial update: render just the results table when filters change

    How it works with HTMX:
      The search form has hx-get pointing to this same URL. When any filter
      input changes, HTMX sends a GET request with all the filter params.
      We check for the HX-Request header to decide what to return:
        - HTMX request → just the results partial (search_results.html)
        - Normal request → the full page (search.html, which includes the partial)

      The hx-push-url="true" attribute on the form tells HTMX to update
      the browser's address bar with the filter params. This makes the
      filtered view bookmarkable and shareable.

    Amount range:
      Amount values are stored as strings in the database (because all
      field values share the same text column). We convert the amount
      filters to floats here so the search service can do numeric comparison.
      If the user types something non-numeric, we just skip that filter
      rather than showing an error.
    """
    # Collect all filter parameters from the query string
    params = {
        "form_type": request.GET.get("form_type", ""),
        "field_key": request.GET.get("field_key", ""),
        "field_value": request.GET.get("field_value", ""),
        "uploaded_from": request.GET.get("uploaded_from", ""),
        "uploaded_to": request.GET.get("uploaded_to", ""),
    }

    # Handle amount range — try to convert to float, skip if invalid
    for key in ("amount_min", "amount_max"):
        raw = request.GET.get(key)
        if raw:
            try:
                params[key] = float(raw)
            except ValueError:
                pass  # ignore non-numeric input, just skip the filter

    # Delegate to the search service — it builds the filtered queryset
    documents = search_documents(params)

    # If this is an HTMX request, return just the results table partial.
    # The full page template also includes this partial, so they stay in sync.
    if request.headers.get("HX-Request"):
        return render(request, "ui/partials/search_results.html", {"documents": documents})

    # Normal page load — return the full page with filters and results
    return render(request, "ui/search.html", {"documents": documents, "params": params})
