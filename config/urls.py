"""
Root URL configuration — the top-level router for the whole project.

We keep this dead simple: three prefixes.
  - /admin/  → Django's built-in admin panel (for debugging/data inspection)
  - /api/    → REST API endpoints (JSON responses, for programmatic access)
  - /        → Web UI pages (HTML responses, for browser-based users)

The UI app handles its own login/logout routes using Django's built-in
auth views, so we don't need to configure them here.

Static/media file serving:
  In development (DEBUG=True), Django serves uploaded files directly.
  In production, you'd use nginx or a CDN instead — Django's static
  file serving is single-threaded and not optimized for file downloads.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),    # JSON API under /api/
    path("", include("ui.urls")),         # HTML pages at the root
]

# Serve uploaded files (PDFs in /media/) during development.
# The static() helper returns an empty list when DEBUG=False,
# so this has no effect in production.
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
