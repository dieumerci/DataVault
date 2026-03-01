"""
Reporting service — the "non-trivial SQL query" requirement.

The assignment asks for at least one reporting endpoint that uses
non-trivial SQL. We implement "top N most frequently corrected field keys".

Why raw SQL instead of Django ORM?
  1. The assignment explicitly wants to see SQL skills
  2. For reporting queries, raw SQL is often clearer than the ORM equivalent
  3. It shows we know when to reach for raw SQL vs when to use the ORM

Safety: we use parameterized queries (%s with params list) — NEVER
f-strings or string concatenation for SQL. That prevents SQL injection.
"""

from django.db import connection


def top_corrections(limit: int = 3, date_from=None, date_to=None):
    """
    Return the top N most frequently corrected field keys.

    "Corrected" means: corrected_value is not null AND it differs
    from the original. (If someone "corrects" a value to the same
    thing, that's not really a correction.)

    Args:
        limit: how many results to return (default 3)
        date_from: optional start date filter on corrected_at
        date_to: optional end date filter on corrected_at

    Returns:
        [{"key": "amount", "correction_count": 12}, ...]
    """

    # Build the WHERE clause dynamically based on which filters are provided.
    # Start with the base conditions that always apply.
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

    # The query:
    # - Filters to only corrected fields
    # - Groups by field key (routing_number, amount, etc.)
    # - Counts how many corrections each key has
    # - Orders by most corrections first
    # - Limits to top N
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

    # Execute the query and convert the cursor rows to dicts.
    # This is the standard pattern for raw SQL in Django.
    with connection.cursor() as cursor:
        cursor.execute(sql, params)
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
