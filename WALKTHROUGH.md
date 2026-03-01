# Video Walkthrough Script

Use this document as your guide while recording your Loom video. Read through it once before recording, then follow the sections in order. Speak naturally — don't read word-for-word. The talk tracks below are starting points; use your own words.

---

## Suggested Video Structure (8-12 minutes)

| Time   | Section                          |
|--------|----------------------------------|
| 0:00   | Quick intro + live demo          |
| 2:00   | Project structure overview       |
| 3:00   | Domain layer — models + services |
| 6:00   | API layer — REST endpoints       |
| 7:30   | UI layer — HTMX templates        |
| 9:00   | Tests + Docker setup             |
| 10:00  | Trade-offs + what I'd do next    |

---

## Part 1: Live Demo (0:00 - 2:00)

> Open the browser at `http://localhost:8000`. Log in with admin/admin.

**Talk track:**

"Let me start by showing you the app in action. This is a Document Intake and Field Correction Service. It handles financial forms like W-9s and ACH authorizations."

### Demo flow — follow these steps on screen:

1. **Upload page** — You'll see two options: PDF upload on the left, JSON payload on the right. The JSON side has a pre-filled example so you can test immediately without needing a real PDF.

2. **Submit the JSON** — Click "Submit JSON". This creates a document with four extracted fields: routing number, account number, amount, and customer name.

3. **Document detail page** — Point out:
   - The metadata card at the top (form type, status, upload time)
   - The fields table with original values, confidence scores, and color-coded confidence bars
   - The inline correction forms — each row has an input field and a Save button

4. **Correct a field** — Type a new value (say, change "Jane Smith" to "Janet Smith") and click Save. Point out:
   - The row updates instantly — no page reload
   - The "Corrected" badge appears
   - Both original and corrected values are visible (audit trail)
   - The green flash animation confirms the update happened

5. **Search page** — Navigate to Search. Show the filter options: form type, field key/value, amount range, date range. Type something in the field value filter and show results updating dynamically.

> "That's the full user flow: upload, review extracted fields, correct mistakes inline, and search across everything. Now let me show you how it's built."

---

## Part 2: Project Structure (2:00 - 3:00)

> Open your editor or terminal and show the folder structure.

**Talk track:**

"I split the project into three Django apps, and there's a specific reason for this separation."

```
Data-Vault/
  config/          <- Django settings and root URL config
  documents/       <- Domain layer: models + business logic
    models.py         All data models live here
    services/         Pure Python functions — no HTTP awareness
      extraction.py      PDF text extraction + regex parsing
      ingestion.py       Document creation orchestrator
      search.py          Filtered queries with COALESCE
      reporting.py       Raw SQL for correction reports
  api/             <- REST layer: JSON endpoints
    serializers.py    Model-to-JSON translation
    views.py          Thin HTTP wrappers around services
    urls.py           Route definitions
  ui/              <- HTML layer: server-rendered pages + HTMX
    views.py          Same thin pattern — calls services, returns HTML
    templates/ui/     Full-page templates
      partials/       HTMX fragment templates (the key pattern)
  templates/        <- Shared templates (login page)
  static/           <- CSS and JS assets
  docker-compose.yml
  Dockerfile
```

**Key point to say out loud:**

"The `documents` app is the core. It owns the models and all business logic in a `services/` package. It knows absolutely nothing about HTTP, JSON, or HTML. The `api` and `ui` apps are both thin consumers of the same service functions. So if I call `ingest_pdf()` from the REST API or from the HTML upload form, it's the exact same function — no duplication. Tomorrow I could add a Celery task or a management command and they'd call the same services too."

---

## Part 3: Domain Layer — `documents/` (3:00 - 6:00)

### 3a. Models (`documents/models.py`)

> Open `documents/models.py` and scroll through it.

**Talk track for Document model:**

"Let me walk you through the two models. The `Document` model represents an uploaded file — could be a W-9, ACH form, loan application, whatever."

Point out these decisions and explain why:

1. **UUID primary key** — "I used UUIDs instead of auto-incrementing integers. In a financial document system, sequential IDs are a security concern because someone could enumerate documents by guessing `/documents/1`, `/documents/2`. UUIDs are non-guessable. They also work well if you ever need to generate IDs before hitting the database."

2. **Status enum** — "I used Django's `TextChoices` for the status field. It gives us validation at the database level — if someone tries to save an invalid status, Django rejects it. We also get `get_status_display()` for human-readable labels in templates. The three states are: `uploaded` (file received), `processed` (extraction ran successfully), and `error` (extraction failed or found nothing)."

3. **FileField with date-based upload_to** — "The `upload_to='documents/%Y/%m/%d/'` organizes files by date. Without this, you'd get thousands of files in one directory, which slows down filesystem operations on Linux. It also makes archiving old files straightforward."

4. **Indexed fields** — "I added database indexes on `form_type`, `uploaded_at`, and `status` because those are the three columns we filter on most in the search page. Without indexes, every search would do a full table scan."

**Talk track for Field model — this is the most important part:**

"The `Field` model is where the core idea lives. Each field is a key-value pair extracted from a document — like `routing_number = 021000021`."

5. **The effective_value concept** — "This is the central design decision. When an ops user corrects a field, I don't overwrite the original value. Instead, I store the correction in a separate `corrected_value` column alongside the `original_value`. Then everywhere I need 'the real value', I use `effective_value`, which is: if a correction exists, use it; otherwise, use the original."

   "In Python, this is a simple `@property` on the model. In the database, it's `COALESCE(corrected_value, original_value)`. Same logic at two levels — Python for display, SQL for queries. This gives us a full audit trail: you can always see what extraction produced versus what a human corrected."

6. **Audit fields** — "The `corrected_at` and `corrected_by` fields track when and who made each correction. In financial systems, you need this audit trail. And `on_delete=SET_NULL` on `corrected_by` means if a user account gets deleted, we keep the correction record — we just lose the link to who did it."

7. **Composite index** — "I added a composite index on `(document, key)` because the search service's most common query is 'find fields for document X with key Y'. This index makes that query use a B-tree lookup instead of scanning every row."

---

### 3b. Services — Extraction (`documents/services/extraction.py`)

> Open `documents/services/extraction.py`.

**Talk track:**

"This is where PDF processing happens. It does two things: pull text out of the PDF, then scan that text for financial fields using regex."

1. **Why pypdf** — "I chose pypdf because it's pure Python with zero system dependencies. No Tesseract, no poppler, nothing to install. This keeps the Docker image small and the build fast. The trade-off is it only handles text-based PDFs, not scanned documents. In production you'd add OCR, but for demonstrating the pipeline, this is the right trade-off."

2. **Separate parser functions** — "Each field type has its own parser function: `_find_routing_number`, `_find_amount`, `_find_customer_name`. They're collected in a list called `_ALL_PARSERS`. This is the Open/Closed Principle — to add a new field type, I write a function and append it to the list. I never touch existing parser code."

3. **Confidence scores** — "Each parser returns a confidence score. Routing numbers get 0.6 because lots of 9-digit numbers exist that aren't routing numbers. Dollar amounts get 0.7 because the `$` sign is a stronger signal. Customer names get 0.4 because the regex is weak — it depends on a label like 'Name:' appearing before the value. These scores tell ops users which fields to double-check first."

4. **The NamedTuple** — "I wrapped the return values in an `ExtractedField` namedtuple. It's immutable and has named attributes, so downstream code reads `field.key` instead of `field[0]`. It's a small thing that makes the code much more readable."

---

### 3c. Services — Ingestion (`documents/services/ingestion.py`)

> Open `documents/services/ingestion.py`.

**Talk track:**

"This is the orchestrator — it coordinates the whole document creation process. There are two entry points: `ingest_pdf()` for file uploads and `ingest_json()` for the test/API path."

1. **PDF validation** — "Before anything else, I validate the file. I check both the MIME type and the filename extension because some browsers send PDFs as `application/octet-stream`. There's also a 10MB size limit. This is defense-in-depth — don't trust the client."

2. **The file.seek(0) detail** — "This is a subtle but critical detail. When Django saves the FileField, it reads the uploaded file to write it to disk. This moves the file pointer to the end. If I then pass the same file object to pypdf, it sees an empty stream and finds no text. `seek(0)` rewinds to the beginning. This is one of those bugs that only appears when you save and extract in the same request."

3. **Error handling philosophy** — "If extraction fails, I set the status to 'error' but I don't delete the document or file. The PDF stays on disk. This is intentional — an ops user can manually enter the fields later, or a developer can debug what went wrong. Deleting the file would mean the user has to re-upload."

4. **bulk_create** — "Instead of creating fields one at a time with N separate INSERT queries, `bulk_create` sends a single INSERT with all rows. With 4 fields the performance difference is tiny, but it's a good habit. If a document has 50 fields from a complex form, this matters."

---

### 3d. Services — Search (`documents/services/search.py`)

> Open `documents/services/search.py`.

**Talk track:**

"The search service builds a filtered queryset from the search form parameters. The interesting part is how it handles corrections."

1. **COALESCE in Django** — "When searching by field value, I need to match against the corrected value if one exists, otherwise the original. I use Django's `Coalesce()` function to compute this at the database level: `annotate(effective=Coalesce('corrected_value', 'original_value'))`. The database does the COALESCE, not Python, so it works correctly with SQL filtering."

2. **Subqueries vs JOINs** — "I use subqueries instead of JOINing Documents to Fields directly. The reason is the multiplication problem: a document with 5 fields would appear 5 times in a JOIN result. You'd need GROUP BY or DISTINCT to de-duplicate, which is slower than the subquery approach. The subquery finds matching Field IDs, then I filter Documents by those IDs."

3. **The .extra() for amount range** — "Amount values are stored as strings because all field values share the same column. To do numeric comparison like 'amount greater than 1000', I need to CAST to NUMERIC in SQL. Django's ORM can't do this natively on annotated text columns, so I use `.extra()` to inject the raw SQL. In production, I'd add a computed column with a functional index instead."

---

### 3e. Services — Reporting (`documents/services/reporting.py`)

> Open `documents/services/reporting.py`.

**Talk track:**

"The assignment asks for at least one endpoint that uses non-trivial SQL. I built a 'top N most frequently corrected field keys' report. This tells you which fields your extraction is getting wrong most often — useful for improving the parsers."

1. **Why raw SQL** — "I could have written this with the ORM, but for a reporting query that returns aggregates rather than model instances, raw SQL is often clearer. It also shows that I'm comfortable writing SQL when it's the right tool."

2. **Dynamic WHERE clause** — "The WHERE clause builds dynamically based on which filters are provided. The base conditions are always there — `corrected_value IS NOT NULL` and `corrected_value <> original_value` — and date filters are appended if present."

3. **SQL injection prevention** — "All actual values go through parameterized `%s` placeholders. Django passes these to the PostgreSQL driver, which escapes them properly. The rule is: SQL structure in Python, user values in params. Never string concatenation with user input."

---

## Part 4: API Layer — `api/` (6:00 - 7:30)

> Open `api/views.py` and `api/serializers.py`.

**Talk track:**

"The API app is a thin REST layer. Each view is under 20 lines of logic because the real work is in services."

### Views (`api/views.py`)

1. **Authentication model** — "Authentication is configured globally in `settings.py` with `IsAuthenticatedOrReadOnly`. This means GET requests are public — anyone can browse documents. But POST, PATCH, DELETE require you to be logged in. For the field correction endpoint, I added an explicit `IsAuthenticated` permission as an extra safety layer."

2. **Smart dispatch on POST** — "The document creation endpoint is smart: if the request contains a file, it runs the PDF ingestion path. If the body is JSON, it runs the JSON path. The view doesn't do any business logic — it figures out which service to call, calls it, and serializes the result. That's the whole pattern."

3. **PATCH-only corrections** — "The field correction endpoint only accepts PATCH, not PUT. We only want partial updates — the client sends just `corrected_value`. The `perform_update` method automatically stamps `corrected_at` and `corrected_by` so the client can't forge audit data."

### Serializers (`api/serializers.py`)

4. **Three serializers** — "I have three serializers for different use cases. `DocumentListSerializer` is lightweight — no nested fields, just a field count. It's used for list endpoints where you might return hundreds of documents. `DocumentDetailSerializer` nests all fields because when you view one document, you want everything. `FieldSerializer` includes the computed `effective_value` as a `SerializerMethodField`."

### Quick API demo (if time permits)

> Show a curl command in terminal:
```bash
# List documents
curl http://localhost:8000/api/documents/

# Get a token
curl -X POST http://localhost:8000/api/token/ -d "username=admin&password=admin"

# Correct a field (use the token)
curl -X PATCH http://localhost:8000/api/fields/1/ \
  -H "Authorization: Token <your-token>" \
  -H "Content-Type: application/json" \
  -d '{"corrected_value": "new value"}'
```

---

## Part 5: UI Layer — `ui/` (7:30 - 9:00)

> Open `ui/views.py` and the templates folder.

**Talk track:**

"The UI app uses HTMX instead of a JavaScript framework. HTMX adds dynamic behavior through HTML attributes — no React, no Vue, no build step. The pages are server-rendered with Django templates and Tailwind CSS."

### The HTMX Pattern

1. **How HTMX works here** — "There are three key HTML attributes that make everything work:
   - `hx-post` tells HTMX which URL to send the POST request to
   - `hx-target` tells it which element on the page to update with the response
   - `hx-swap='outerHTML'` tells it to replace the entire target element, not just its contents

   So when a user saves a field correction, HTMX sends a POST, the server returns just the updated table row as HTML, and HTMX swaps the old row with the new one. No JSON parsing, no state management, no JavaScript."

### The Partial Template Pattern

2. **One template, two uses** — "This is the most important pattern in the UI. The `field_row.html` partial template is used in two places:
   - During the initial page load, it's included inside a for loop: `{% include 'ui/partials/field_row.html' %}`
   - When a field gets corrected, the `correct_field` view returns this exact same template

   Because it's the same template, the updated row always looks identical to what was there before. There's no synchronization problem. One template, two uses, zero drift."

### The Search Page

3. **Dynamic search** — "The search page uses `hx-get` on the filter form. When any filter changes, HTMX sends the parameters to the same URL. The view checks for the `HX-Request` header — if it's an HTMX request, it returns just the results table partial. If it's a normal page load, it returns the full page. The `hx-push-url='true'` attribute updates the browser's address bar so the URL is bookmarkable."

### Views Pattern

4. **Thin views** — "Every UI view follows the same pattern: parse the request, call a service function, render a template. The upload view calls `ingest_pdf()` or `ingest_json()`. The search view calls `search_documents()`. The correction view updates the field and returns the partial. No view has more than 20 lines of actual logic."

---

## Part 6: Tests + Docker (9:00 - 10:00)

> Run the tests and show them passing.

```bash
docker compose exec web python manage.py test
```

**Talk track:**

"I wrote 16 tests targeting the highest-value scenarios — the things that would break the app if they regressed."

### What I chose to test and why

1. **Effective value (3 tests)** — "This is the core concept. If effective_value breaks, both search and display break. I test the three cases: no correction, correction exists, and correction is explicitly None."

2. **Extraction (4 tests)** — "Regex is inherently brittle. These tests lock in the exact patterns I expect: routing numbers, dollar amounts, customer names, and the edge case of empty text."

3. **JSON ingestion (2 tests)** — "Happy path plus validation. I make sure empty field lists are rejected — you shouldn't be able to create a document with zero fields via the JSON path."

4. **PDF validation (2 tests)** — "Browsers sometimes send PDFs as `application/octet-stream`. I test that the fallback to filename extension works, and that non-PDF files are properly rejected."

5. **Auth (tested via API)** — "Anonymous PATCH is blocked. Authenticated PATCH works and stamps `corrected_by` with the user who made the change."

6. **Search with corrections** — "The critical one: searching for a value that was corrected should find the corrected version, not the original. This proves COALESCE works at the database level."

### Docker Setup

> Show `docker-compose.yml` briefly.

"Two services: Postgres and Django. That's it — no Redis, no Celery, no nginx. The `depends_on` with `service_healthy` ensures the Django container waits until Postgres is actually accepting connections, not just 'the container started'. Gunicorn's timeout is 120 seconds because PDF extraction can be slow on large files."

---

## Part 7: Trade-offs and What I'd Do Next (10:00 - end)

**Talk track:**

"Let me talk about trade-offs. Every engineering decision has them, and I want to be upfront about mine."

### Trade-offs I made

1. **Synchronous PDF extraction** — "Right now, extraction happens in the request cycle. The user waits while the PDF is being processed. For a small file that's fine, but for a 50-page PDF it could take several seconds. The fix is Celery: return immediately with `status=uploaded`, queue a background task, and update the status when extraction finishes. My service layer already supports this — `ingest_pdf()` is a plain Python function with no HTTP dependencies, so it can run in a Celery worker without changes."

2. **Regex-based extraction** — "I used simple regex patterns for field extraction. They work on text-based PDFs but miss scanned documents entirely. In production, you'd add OCR with Tesseract or a cloud service like AWS Textract. The important thing is the `parse_fields()` interface is designed for swappability — you can replace the regex parsers with ML models without changing the ingestion pipeline."

3. **No UI pagination** — "The search results page doesn't paginate. The API does — DRF's `PageNumberPagination` is configured globally in settings. Adding pagination to the UI is straightforward — just add page links and pass the page number through the search service."

4. **The `.extra()` usage** — "For the amount range filter, I used Django's `.extra()` to inject a CAST in raw SQL. The ORM can't natively cast annotated text fields to numeric types. In production, I'd either add a computed column with a functional index, or use `RawSQL` expressions."

### What I'd build next

1. **Celery** — Background PDF extraction so the user doesn't wait
2. **OCR** — Tesseract or AWS Textract for scanned documents
3. **Audit log** — Track all field changes over time with `django-simple-history`
4. **Full-text search** — PostgreSQL's built-in `tsvector` on extracted text
5. **CI/CD** — GitHub Actions running `docker compose exec web python manage.py test`
6. **Rate limiting** — Protect upload endpoints from abuse

---

## Quick Reference: Requirement Checklist

Use this to verify you've covered everything the assignment asked for:

| # | Requirement | Where it lives |
|---|-------------|----------------|
| 1 | Ingest PDF documents | `documents/services/ingestion.py` -> `ingest_pdf()` |
| 2 | Extract text from PDF | `documents/services/extraction.py` -> `extract_text_from_pdf()` |
| 3 | Parse fields (key, value, type, confidence) | `extraction.py` -> `parse_fields()` + individual parsers |
| 4 | Store extracted fields in PostgreSQL | `documents/models.py` -> `Field` model, `ingestion.py` -> `_bulk_create_fields()` |
| 5 | Correct field values (keep original) | `Field.corrected_value` + `effective_value` property |
| 6 | Track who corrected and when | `Field.corrected_at` + `Field.corrected_by` |
| 7 | Search/filter documents | `documents/services/search.py` -> `search_documents()` |
| 8 | Search uses corrected values | `Coalesce("corrected_value", "original_value")` in search.py |
| 9 | REST API for CRUD | `api/views.py` -> `DocumentListCreateView`, `DocumentDetailView` |
| 10 | REST API for corrections | `api/views.py` -> `FieldCorrectionView` (PATCH only) |
| 11 | API auth (read=public, write=auth) | `settings.py` -> `IsAuthenticatedOrReadOnly` |
| 12 | Token-based auth | `rest_framework.authentication.TokenAuthentication` |
| 13 | Reporting endpoint with SQL | `api/views.py` -> `TopCorrectionsView`, `reporting.py` -> raw SQL |
| 14 | Non-trivial SQL query | `reporting.py` -> GROUP BY + COUNT + ORDER BY + LIMIT |
| 15 | Web UI for upload | `ui/templates/ui/upload.html` (PDF + JSON forms) |
| 16 | Web UI for document detail | `ui/templates/ui/document_detail.html` |
| 17 | Web UI for inline corrections | `ui/templates/ui/partials/field_row.html` (HTMX) |
| 18 | Web UI for search | `ui/templates/ui/search.html` + `search_results.html` |
| 19 | Login required for mutations | `@login_required` on upload + correct_field views |
| 20 | PostgreSQL database | `settings.py` -> `django.db.backends.postgresql` |
| 21 | Docker Compose setup | `docker-compose.yml` + `Dockerfile` |
| 22 | Database indexes | `models.py` -> `db_index=True` on 4 fields + composite index |
| 23 | Automated tests | `documents/tests.py` -> 16 tests |
| 24 | README with setup instructions | `README.md` -> Docker + Local setup |
| 25 | Clean code with documentation | Docstrings + inline comments throughout |
| 26 | Solution explanation | `SOLUTION.md` -> Architecture + trade-offs |

---

## Tips for Recording

- **Show, don't tell** — Keep the browser or editor visible. Point at the code as you talk about it.
- **Use the demo first** — Starting with the working app gives the interviewer context for the code walkthrough.
- **Name the files** — Say "opening `extraction.py` in the services folder" so the viewer can follow along.
- **Hit the trade-offs** — Interviewers care more about what you'd improve than what you built. Spend time on Part 7.
- **Stay under 12 minutes** — Concise > comprehensive. If you're running long, cut the curl demo and skip to trade-offs.
- **Be honest about AI** — If asked, explain that you used AI as a scaffolding and research partner. You drove the architecture decisions, the AI helped with boilerplate and documentation. The thinking is yours; the typing got a boost.
