# Solution — Data Vault

## What I Built

A Document Intake & Field Correction Service for financial documents. The idea is simple — banks and financial institutions receive forms (W-9s, ACH authorizations, loan applications), and someone needs to pull the data out, review it, and fix any mistakes.

Here's the flow:

- User uploads a document (PDF or JSON)
- System extracts key fields like routing numbers, amounts, and customer names
- An ops user reviews the extracted data and corrects any mistakes inline
- The corrected value becomes the source of truth, but the original is never lost

I built this as a Django monolith with three apps, a REST API, and an HTMX-powered UI. The whole thing runs in Docker with two containers.

---

## Recording Your Video

- Use Loom, make sure your audio works before you start
- Focus on **why** you made choices — don't just walk through the code
- Cover what you chose, what the alternatives were, and why you didn't pick them
- The reviewers care about your thinking process, not just the end result

---

## File Structure

```
Data-Vault/
├── config/                 # Django settings, URLs, WSGI
├── documents/              # Domain layer (models + services)
│   ├── models.py             Document + Field models
│   └── services/
│       ├── extraction.py     PDF text extraction + regex
│       ├── ingestion.py      Document creation orchestrator
│       ├── search.py         Filtered queries with COALESCE
│       └── reporting.py      Raw SQL for correction reports
├── api/                    # REST layer (JSON endpoints)
│   ├── serializers.py
│   ├── views.py
│   └── tests.py
├── ui/                     # Web layer (HTML + HTMX)
│   ├── views.py
│   └── templates/ui/
│       ├── base.html
│       ├── upload.html
│       ├── document_detail.html
│       ├── search.html
│       └── partials/
│           ├── field_row.html
│           └── search_results.html
├── docker-compose.yml
├── Dockerfile
├── Makefile
└── requirements.txt
```

---

## Architecture — Three Apps

I split the project into three Django apps instead of cramming everything into one:

- `documents/` — the domain layer, owns all business logic and models
- `api/` — the REST layer, thin views that return JSON
- `ui/` — the web layer, thin views that return HTML via HTMX

**Why I did it this way:**
- I wanted business logic to live in one place. If `ingest_pdf()` needs to change, I change it once in `documents/services/ingestion.py` and both the API and UI get the update automatically
- Views stay thin — most are under 20 lines. They just handle HTTP (parse the request, call a service, return a response)
- Services are plain Python functions with no HTTP awareness, which makes them really easy to test. No need to mock requests or responses
- If I needed to add a CLI command or a Celery worker tomorrow, they'd just call the same service functions

**Trade-off:**
- It's one extra directory compared to a single app with fat views
- But fat views couple your business logic to HTTP and force you to duplicate code when you need the same logic in two places. I'd rather have the extra directory

---

## Design Decisions

### 1. Effective Value — the most important decision

This is the core concept of the whole project. When an ops user corrects a field, I don't overwrite the original. Both values sit side by side, and the system figures out which one to use on the fly.

**Why I did it this way:**
- In financial systems, you can't just throw away the original data. If someone corrects a routing number from `8707114422081` to `9707114422081`, I need to know what the system originally extracted
- Corrections are reversible — clear the `corrected_value` and the original comes back
- Search automatically uses the corrected value when it exists, so users always find the latest data

**How it works across three layers:**

In the model (`documents/models.py`):
```python
@property
def effective_value(self):
    if self.corrected_value is not None:
        return self.corrected_value
    return self.original_value
```

In search queries (`documents/services/search.py`):
```python
Field.objects
    .annotate(effective=Coalesce("corrected_value", "original_value"))
    .filter(key=field_key, effective__icontains=field_value)
```

In the reporting SQL (`documents/services/reporting.py`):
```sql
COALESCE(corrected_value, original_value)
```

The same idea — "use the correction if it exists, otherwise use the original" — expressed in Python, the ORM, and raw SQL depending on what the context needs.

**What I decided not to do:**
- I didn't build a `FieldHistory` table to track every single correction over time. For this scope, storing the latest correction with `corrected_at` and `corrected_by` is enough. If I needed full history, I'd reach for `django-simple-history` — it's a one-line addition to the model

---

### 2. PDF Extraction — Regex, not ML or OCR

I used regex to pull fields out of PDFs. Each parser is a small function that takes text and returns matches with a confidence score:

```python
_ROUTING_RE = re.compile(r"\b(\d{9})\b")

def _find_routing_number(text: str) -> list[ExtractedField]:
    match = _ROUTING_RE.search(text)
    if match:
        return [ExtractedField("routing_number", match.group(1), "string", 0.6)]
    return []
```

All parsers live in a list, so adding a new one is just appending to the list:
```python
_ALL_PARSERS = [
    _find_routing_number,
    _find_account_number,
    _find_amount,
    _find_customer_name,
]
```

**Why I did it this way:**
- Zero system dependencies — no Tesseract to install, no AWS credentials to manage
- Docker image stays small (~150MB instead of 900MB+ with OCR libraries)
- Regex is deterministic — the same input always gives the same output, which makes testing straightforward
- It's enough to demonstrate the full pipeline. The architecture is what matters here, not the extraction accuracy

**Trade-off:**
- Regex only works on text-based PDFs. Scanned documents would need OCR
- But the `parse_fields()` interface is designed so you could swap in a Tesseract or Textract extractor without touching the ingestion pipeline. I scoped OCR out intentionally, not because I forgot about it

---

### 3. Frontend — HTMX, not React

I went with server-rendered HTML and HTMX instead of a JavaScript framework. The key pattern is partial templates — here's `field_row.html`, which renders a single table row with an inline correction form:

```html
<tr class="field-row" id="field-{{ field.id }}">
    <!-- ... field data columns ... -->
    <td>
        <form hx-post="{% url 'ui:correct_field' pk=field.pk %}"
              hx-target="#field-{{ field.id }}"
              hx-swap="outerHTML">
            {% csrf_token %}
            <input type="text" name="corrected_value" placeholder="Correct...">
            <button type="submit">Save</button>
        </form>
    </td>
</tr>
```

When the user clicks Save, HTMX sends a POST, the server returns this same template with updated data, and HTMX swaps the old row for the new one. The row flashes green briefly (CSS transition) so the user sees the change happened. No JavaScript needed.

**Why I did it this way:**
- This app is forms and tables — HTMX handles that with about 10% of the complexity of React
- No JS build step, no node_modules, no webpack config, no client-side state to manage
- Django already renders HTML — HTMX just makes it dynamic
- The partial template pattern means the initial render and the HTMX response use the exact same template, so they can never get out of sync

**Trade-off:**
- HTMX wouldn't be the right choice if I needed drag-and-drop, real-time collaboration, or offline support
- But for CRUD operations and form submissions, a full JS framework would be over-engineering

---

### 4. Synchronous Processing

**Why I did it this way:**
- User uploads a PDF, waits 1-2 seconds, and sees the extracted fields. Simple and easy to debug
- No extra infrastructure to set up or maintain
- The response is fast enough for demo-sized files

**Trade-off:**
- It blocks the request thread during extraction. For large PDFs or high traffic, this wouldn't work
- In production, I'd return `201 Created` immediately and queue a Celery task for extraction
- The good news is the service layer already supports this — `ingest_pdf()` is a plain function with no HTTP dependencies, so moving it into a Celery worker is just calling the same function from a different place

**What I decided not to do:**
- No Celery + Redis — that's two more services in docker-compose, and it doesn't prove anything the services pattern doesn't already show

---

### 5. Authentication — Django's Built-in Auth

**Why I did it this way:**
- SessionAuth for the browser UI (login form, CSRF protection, cookie-based sessions)
- TokenAuth for API clients (`Authorization: Token <key>`)
- Global permission set to `IsAuthenticatedOrReadOnly` — anyone can browse, but you need to log in to make changes
- I added an explicit `IsAuthenticated` check on the correction endpoint as defense-in-depth

**Trade-off:**
- Session-based auth is tied to the server. In a microservices setup, you'd want something stateless like JWT
- But this is a monolith. Django has session support built in. Adding JWT would mean managing token refresh, blacklisting, and a library like `djangorestframework-simplejwt` — all complexity with no benefit here

**What I decided not to do:**
- No JWT — wrong tool for a monolith
- No custom registration flow — the assignment needs auth for data-modifying endpoints, not a signup page. `createsuperuser` + Django's `LoginView` gets the job done

---

### 6. Search — Subqueries Over JOINs

The search service (`documents/services/search.py`) finds documents based on form type, date range, field values, and amount ranges. Here's the tricky part — the field-level search:

```python
matching_doc_ids = (
    Field.objects
    .annotate(effective=Coalesce("corrected_value", "original_value"))
    .filter(key=field_key, effective__icontains=field_value)
    .values_list("document_id", flat=True)
)
qs = qs.filter(id__in=matching_doc_ids)
```

**Why subqueries instead of JOINs:**
- If you JOIN Documents to Fields directly, a document with 5 fields shows up 5 times in the results. That's the multiplication problem
- You'd need GROUP BY or DISTINCT to fix it, which adds complexity and hurts performance
- The subquery approach avoids this entirely — find the matching field IDs first, then filter documents by those IDs

**The amount range challenge:**
- Field values are all stored as text because different field types (strings, numbers, dates) share one column
- To do numeric comparisons on amount fields, I need `CAST(COALESCE(...) AS NUMERIC)` in SQL
- The Django ORM can't do that natively, so I used `.extra()` with parameterized queries
- In production, I'd add a functional index or a computed column instead

---

### 7. Reporting — Raw SQL

The assignment asks for a non-trivial SQL query, so I built a "top corrected fields" report:

```python
sql = """
    SELECT key, COUNT(*) AS correction_count
    FROM documents_field
    WHERE corrected_value IS NOT NULL
      AND corrected_value <> original_value
    GROUP BY key
    ORDER BY correction_count DESC
    LIMIT %s
"""
```

**Why raw SQL here:**
- The assignment explicitly asks for it
- Aggregate queries (COUNT, GROUP BY, ORDER BY) read more naturally in SQL than the ORM equivalent
- All parameters are passed through `%s` placeholders — no string formatting, no SQL injection risk

**Trade-off:**
- I use the ORM everywhere else (CRUD, search, model operations). Raw SQL is reserved for reporting where I'm returning numbers, not model instances
- Each tool where it fits best

---

### 8. Database Design

A few decisions worth calling out:

- **UUID primary keys** — sequential IDs like `/documents/1`, `/documents/2` let anyone guess valid URLs. UUIDs are non-guessable and globally unique. Slightly more storage, but worth it for financial data
- **Nullable `corrected_value`** — NULL means "no correction has been made." An empty string would be ambiguous — did they correct it to nothing, or was it never corrected?
- **`on_delete=SET_NULL` for `corrected_by`** — if an admin deletes a user account, I don't want their corrections to vanish. CASCADE would destroy the audit trail. SET_NULL keeps the correction but orphans the user reference
- **Composite index on `(document, key)`** — the search service filters fields by document and key together, so this index speeds up the most common query pattern

---

## Testing (16 Tests)

I focused testing on the parts most likely to break and most expensive if they do:

- **Effective value (3 tests)** — this is the core concept. If it breaks, both the display and search are wrong
- **Extraction parsers (4 tests)** — regex is brittle by nature. These tests lock in the expected patterns so I know immediately if a change breaks extraction
- **JSON ingestion (2 tests)** — happy path plus validation (empty fields get rejected)
- **PDF validation (2 tests)** — browsers sometimes send `application/octet-stream` instead of `application/pdf`. These tests make sure both are accepted
- **Auth enforcement (2 tests)** — anonymous user can't correct fields, authenticated user can, and the audit trail (who + when) is recorded
- **Reporting SQL (1 test)** — raw SQL is easy to get wrong. This test runs the full aggregate query end-to-end
- **Search with corrections (2 tests)** — the most important tests in the project

**The most important test:** I correct "John Smith" to "Jane Doe," then search for "Jane" — it finds the document. Search for "John" — it doesn't. This proves the effective value concept works all the way through the database, not just in Python.

**What I decided not to test:**
- No frontend tests (Selenium/Playwright) — the real value is in testing business logic and data integrity, not button clicks
- No 100% coverage target — I'd rather have 16 meaningful tests than 60 tests that just check trivial getters

---

## Docker

- Two services only: PostgreSQL and Django running behind Gunicorn
- `depends_on` with `service_healthy` — Django waits for Postgres to actually accept connections, not just for the container to start. Without this, migrations fail on first boot because Postgres is still initializing
- Python 3.12-slim base image — 150MB vs 900MB for the full image
- Dockerfile layer ordering — I copy `requirements.txt` before the app code. That way Docker caches the pip install layer, and changing a Python file doesn't re-download all dependencies
- No Redis, Celery, or Nginx — keeping it to two containers makes it easier to clone and run

---

## What I'd Build Next

If I had more time, in priority order:

1. **Celery + Redis** — move PDF extraction to a background worker so uploads return instantly
2. **OCR support** — Tesseract or AWS Textract for scanned documents
3. **Correction history** — `django-simple-history` to track every correction, not just the latest one
4. **UI pagination** — the API already paginates via DRF, the UI just needs page links
5. **CI/CD** — GitHub Actions running the Docker test suite on every push
6. **File scanning** — ClamAV to check uploads before extraction
7. **Full-text search** — PostgreSQL `tsvector` for more powerful field value search
8. **Rate limiting** — throttle upload endpoints to prevent abuse

---

## Video Guide

**Suggested flow (8-12 minutes):**

1. **Start with the live demo** — upload a document, correct a field, search for it. This gives the reviewer context for everything you talk about after
2. **Architecture** — show the three-app structure, explain the services pattern
3. **Walk through the domain layer** — models, effective value, extraction pipeline
4. **Show the API layer** — REST endpoints, auth setup, serializers
5. **Explain the HTMX pattern** — partial templates, how a correction works without page reload
6. **Talk through testing** — which tests matter most and why
7. **Close with trade-offs** — what you'd change for production, what you intentionally scoped out

**Tips:**
- Speak to the "why" more than the "what" — they can read the code, they can't read your mind
- Don't read code line by line — point at a key section and explain the decision behind it
- The trade-offs section is your chance to show maturity. Saying "I chose not to do X because Y" is more impressive than just having done everything
- Keep it conversational — imagine you're explaining it to a colleague, not presenting to an audience
