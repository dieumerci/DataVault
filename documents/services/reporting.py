# Reporting service — the "non-trivial SQL query" requirement.

from django.db import connection

def top_corrections(limit: int = 3, date_from=None, date_to=None):

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
