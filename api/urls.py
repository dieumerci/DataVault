"""
API URL routes.

All endpoints live under /api/ (configured in config/urls.py).

We use explicit path() calls instead of a DRF router because we only
have a handful of endpoints and explicit is better than implicit.
A DRF router auto-generates URLs from viewsets, but our views are
class-based API views (not viewsets), so path() is the natural fit.

URL design:
  - /api/documents/         → list + create (GET, POST)
  - /api/documents/<uuid>/  → detail (GET)
  - /api/fields/<id>/       → correction (PATCH)
  - /api/reports/...        → reporting endpoints (GET)
"""

from django.urls import path
from . import views

app_name = "api"

urlpatterns = [
    # Document endpoints — list/create and retrieve
    path("documents/", views.DocumentListCreateView.as_view(), name="document-list"),
    path("documents/<uuid:pk>/", views.DocumentDetailView.as_view(), name="document-detail"),

    # Field correction endpoint — PATCH only (no GET, no PUT)
    path("fields/<int:pk>/", views.FieldCorrectionView.as_view(), name="field-correction"),

    # Reporting — the "non-trivial SQL" requirement
    path("reports/top-corrections/", views.TopCorrectionsView.as_view(), name="top-corrections"),
]
