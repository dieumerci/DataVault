# How the Effective Value Works Across Three Layers

The most important concept in this project is the **effective value** — the idea that when someone corrects a field, we don't throw away the original. We keep both, and the system figures out which one to use depending on the context.

The same logic — "use the correction if it exists, otherwise use the original" — shows up in three different places, each written in a different language because each layer has different needs.

---

## Layer 1: Python Property — for display

**File:** `documents/models.py`

```python
class Field(models.Model):
    original_value = models.TextField()
    corrected_value = models.TextField(null=True, blank=True)

    @property
    def effective_value(self):
        if self.corrected_value is not None:
            return self.corrected_value
        return self.original_value
```

**What it does:**
- When you have a `Field` object in Python and you ask for `field.effective_value`, it checks if there's a correction and returns it. If not, it returns the original
- `corrected_value` is nullable — `None` means "nobody has corrected this yet"

**Where it gets used:**

In the **UI template** (`ui/templates/ui/partials/field_row.html`):
```html
<td>
    <span class="text-sm font-semibold">{{ field.effective_value }}</span>
</td>
```
The template just calls `{{ field.effective_value }}` and gets the right answer. It doesn't need to know if the field was corrected or not — the property handles that decision.

In the **API serializer** (`api/serializers.py`):
```python
class FieldSerializer(serializers.ModelSerializer):
    effective_value = serializers.SerializerMethodField()

    def get_effective_value(self, obj):
        return obj.effective_value
```
DRF can't automatically serialize a Python `@property` (it only knows about database columns), so we use `SerializerMethodField` to call the same property and include it in the JSON response. The API output looks like:
```json
{
    "key": "routing_number",
    "original_value": "8707114422081",
    "corrected_value": "9707114422081",
    "effective_value": "9707114422081"
}
```
The client gets all three values and can show whatever it needs.

**Why a property and not a database column:**
- A stored column would get stale — you'd have to update it every time `corrected_value` changes
- A property computes the answer from the current data every time, so it's always correct
- It's the simplest solution that works. No triggers, no signals, no extra writes

---

## Layer 2: Django ORM — for search

**File:** `documents/services/search.py`

```python
from django.db.models.functions import Coalesce

def search_documents(params: dict):
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
```

**What it does:**
- When a user searches for a field value, we need to search against the effective value, not just the original or corrected
- `Coalesce("corrected_value", "original_value")` tells the ORM to generate SQL that picks the first non-null value
- The `.annotate()` creates a temporary column called `effective` on each row
- Then `.filter(effective__icontains=field_value)` searches against that computed column

**Why we can't use the Python property here:**
- The property only works when you already have a Field object loaded into Python
- Search needs to filter at the database level — we can't load every field into Python and then filter. That would be slow and waste memory
- `Coalesce` pushes the logic down to PostgreSQL, so the database does the filtering for us

**Real-world example:**
1. You upload a document with `customer_name = "John Smith"`
2. You correct it to `"Jane Doe"`
3. You search for `"Jane"` → the database sees `COALESCE('Jane Doe', 'John Smith')` = `'Jane Doe'`, which contains `'Jane'` → match found
4. You search for `"John"` → the database sees `COALESCE('Jane Doe', 'John Smith')` = `'Jane Doe'`, which does NOT contain `'John'` → no match

This is the behaviour we want. The search always uses the latest data.

**The amount range is trickier:**

```python
amount_fields = amount_fields.extra(
    where=["CAST(COALESCE(corrected_value, original_value) AS NUMERIC) >= %s"],
    params=[amount_min],
)
```

All field values are stored as text (because different types like strings, numbers, and dates share the same column). To compare amounts numerically, we need `CAST(... AS NUMERIC)`. Django's ORM can't do a CAST on a COALESCE result natively, so I used `.extra()` with parameterized SQL. It's not pretty, but it's safe (no SQL injection) and it works. In production, I'd add a functional index or a computed column instead.

---

## Layer 3: Raw SQL — for reporting

**File:** `documents/services/reporting.py`

```python
from django.db import connection

def top_corrections(limit: int = 3, date_from=None, date_to=None):
    conditions = [
        "corrected_value IS NOT NULL",
        "corrected_value <> original_value",
    ]
    params = []

    if date_from:
        conditions.append("corrected_at >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("corrected_at <= %s")
        params.append(date_to)

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT
            key,
            COUNT(*) AS correction_count
        FROM documents_field
        WHERE {where_clause}
        GROUP BY key
        ORDER BY correction_count DESC
        LIMIT %s
    """
    params.append(limit)

    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
```

**What it does:**
- This answers the question: "Which field keys get corrected the most?"
- It counts how many times each field key has been corrected, then returns the top N
- The WHERE clause checks `corrected_value IS NOT NULL` (field was corrected) and `corrected_value <> original_value` (the correction actually changed something)

**Why raw SQL here instead of the ORM:**
- The assignment explicitly asks for a non-trivial SQL query
- Aggregate queries with GROUP BY, COUNT, ORDER BY, and LIMIT read more naturally in SQL
- This query returns numbers, not model instances — there's no Field or Document object to hydrate. Raw SQL is a better fit for that
- All user-provided values go through `%s` parameter placeholders. Django passes them to PostgreSQL separately from the SQL string, so there's no way to inject malicious SQL

**Why not raw SQL everywhere:**
- The ORM is better for CRUD where you want model instances with properties and methods
- The ORM handles SQL injection protection automatically — you don't have to think about it
- I use each tool where it makes the most sense: ORM for reads/writes, raw SQL for reporting

---

## How the three layers connect

Here's the full picture of what happens when you correct a field:

**Step 1 — The correction (UI or API)**

UI path (`ui/views.py`):
```python
def correct_field(request, pk):
    field = get_object_or_404(Field, pk=pk)
    field.corrected_value = request.POST.get("corrected_value").strip()
    field.corrected_at = timezone.now()
    field.corrected_by = request.user
    field.save(update_fields=["corrected_value", "corrected_at", "corrected_by"])
    return render(request, "ui/partials/field_row.html", {"field": field})
```

API path (`api/views.py`):
```python
class FieldCorrectionView(generics.UpdateAPIView):
    permission_classes = [permissions.IsAuthenticated]
    http_method_names = ["patch"]

    def perform_update(self, serializer):
        serializer.save(
            corrected_at=timezone.now(),
            corrected_by=self.request.user,
        )
```

Both paths do the same thing — set `corrected_value`, stamp who did it and when, save. The UI returns an HTML partial, the API returns JSON. Same data, different format.

**Step 2 — Display uses the Python property (Layer 1)**

The template renders `{{ field.effective_value }}` which calls the `@property`. If there's a correction, it shows that. If not, it shows the original. The API serializer does the same thing through `SerializerMethodField`.

**Step 3 — Search uses the ORM annotation (Layer 2)**

When someone searches, `Coalesce("corrected_value", "original_value")` ensures the search hits the corrected value. So if you corrected "John Smith" to "Jane Doe" and search for "Jane", you find the document. The original "John Smith" is still in the database, but the search ignores it because the correction takes priority.

**Step 4 — Reporting uses raw SQL (Layer 3)**

The reporting query counts corrections across all fields. It uses `corrected_value IS NOT NULL` to find corrected fields and `corrected_value <> original_value` to exclude no-op corrections (where someone "corrected" a value to the same thing).

---

## Why three implementations of the same idea?

It comes down to what each layer needs:

| Layer | Language | Why this layer exists |
|-------|----------|---------------------|
| Python property | Python | Fast, simple, works when you already have the object in memory. Used for display in templates and API responses |
| ORM annotation | Django/SQL | Pushes the logic to the database so we can filter millions of rows without loading them into Python. Used for search |
| Raw SQL | SQL | Full control over the query for complex aggregates. Used for reporting where we need COUNT + GROUP BY |

If I only had the Python property, search would have to load every field into memory and filter in Python — that doesn't scale. If I only had raw SQL, I'd be writing SQL for simple display logic — that's overkill. Each layer picks the right tool for what it's doing.

The key insight is that all three are expressing the same business rule: **"the corrected value wins."** They just express it in the language that makes sense for their context.
