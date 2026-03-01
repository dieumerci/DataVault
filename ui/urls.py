"""
UI URL routes.

These are the user-facing HTML pages. All routes live at the root
(no /ui/ prefix) because the web interface IS the main experience.

Login and logout use Django's built-in auth views — no need to write
our own authentication logic when Django handles password hashing,
session management, and CSRF protection out of the box.
"""

from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

# app_name lets us reference URLs as "ui:upload", "ui:search", etc.
# in templates: {% url 'ui:upload' %} and in views: redirect("ui:upload")
app_name = "ui"

urlpatterns = [
    # Home — redirects to the upload page (the natural starting point)
    path("", views.index, name="index"),

    # Upload page — PDF file upload or JSON textarea submission
    path("upload/", views.upload, name="upload"),

    # Document detail — shows all fields with inline HTMX editing
    # The <uuid:pk> converter automatically validates UUID format
    path("documents/<uuid:pk>/", views.document_detail, name="document_detail"),

    # HTMX endpoint for field corrections — returns just the updated <tr>
    # This is a POST-only endpoint called by the inline edit forms
    path("fields/<int:pk>/correct/", views.correct_field, name="correct_field"),

    # Search page — 7 filters with HTMX-powered dynamic results
    path("search/", views.search, name="search"),

    # Auth — Django's built-in views handle login/logout for us.
    # We just point them to our custom template for the login page.
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
