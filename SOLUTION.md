# Solution Notes

## Architecture

I split the project into three Django apps:

- **`documents`** — the domain layer. Owns the models and all business logic in a `services/` package. Knows nothing about HTTP, serialization, or templates.
- **`api`** — thin REST layer. DRF serializers and views that translate between HTTP and the service functions.
- **`ui`** — HTMX-powered HTML pages. Also calls the same service functions.

The benefit: the ingestion, search, and reporting logic can be called from the API, the UI, a management command, or a future Celery task — same code, no duplication.

## Key Design Decisions

### Effective Value = COALESCE(corrected_value, original_value)

This is the core concept. When a field gets corrected, we keep both values and compute "effective value" on the fly:

- **In Python**: `Field.effective_value` property
- **In SQL**: `COALESCE(corrected_value, original_value)` via Django's `Coalesce()` annotation
- **In raw SQL**: directly in the reporting query

This means search results automatically reflect corrections, and we maintain a full audit trail.

### Services Layer (Thin Views)

Every view is under 20 lines of logic. The real work happens in:

| Service | What it does |
|---------|-------------|
| `extraction.py` | Pulls text from PDFs, runs regex parsers |
| `ingestion.py` | Orchestrates document creation (PDF or JSON path) |
| `search.py` | Builds filtered querysets with COALESCE |
| `reporting.py` | Raw SQL for correction frequency report |

### HTMX for Dynamic UI

Instead of building a React/Vue frontend, I used HTMX. It adds dynamic behavior through HTML attributes:

- `hx-post`: sends a POST request when a form submits
- `hx-target`: which element to update with the response
- `hx-swap="outerHTML"`: replace the entire target element

The field correction flow: user edits a value → HTMX POSTs to the server → server returns the updated `<tr>` → HTMX swaps it in. No JavaScript written, no JSON parsing, no state management.

## Trade-offs

### Synchronous PDF Extraction

PDF extraction happens in the request cycle. This blocks the web worker for a few seconds on large files. The fix would be:

1. Return immediately with `status=uploaded`
2. Queue a Celery task to extract fields
3. Update status when done

The service layer already supports this — `ingest_pdf()` is a plain function with no HTTP dependencies.

### Simple Regex Extraction

The field parsers use basic patterns (9-digit routing numbers, dollar amounts, labeled names). They won't catch:
- Scanned/image PDFs (needs OCR)
- Unusual field layouts
- Multi-line values

For this take-home, regex demonstrates the pipeline without external dependencies. The `parse_fields()` interface is designed so parsers can be swapped out.

### `.extra()` for Amount Range

The amount range filter uses Django's `.extra()` to inject `CAST(COALESCE(...) AS NUMERIC)`. The ORM can't natively cast annotated text fields to numeric. In production I'd add a computed column or use `RawSQL` expressions instead.

## Indexing

- `Document.form_type` — most common filter
- `Document.uploaded_at` — date range queries
- `Document.status` — status filtering
- `Field.key` — field-level lookups
- `(Field.document, Field.key)` — composite index for the join pattern in search

## Why Raw SQL for the Report

The top-corrections query uses raw SQL because:

1. The assignment asks for at least one non-trivial SQL query
2. Reporting queries that return aggregates (not model instances) are a natural fit for raw SQL
3. It's arguably more readable than the ORM equivalent: `Field.objects.filter(...).values("key").annotate(count=Count("id")).order_by("-count")[:3]`

All user inputs go through parameterized `%s` placeholders — no SQL injection risk.

## What I'd Do Next

1. **Celery** — background PDF extraction
2. **OCR** — Tesseract or AWS Textract for scanned documents
3. **Audit log** — track all field changes over time
4. **Pagination in UI** — the search results need pagination for large datasets
5. **File virus scanning** — validate PDFs with ClamAV
6. **CI/CD** — GitHub Actions using the Docker setup
