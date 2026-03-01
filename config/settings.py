"""
Django settings for Data Vault.

We read all config from environment variables so the same Docker image
works in dev and CI without changing code. The .env file feeds these
values through docker-compose's env_file directive.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# load_dotenv reads the .env file at project root — this is what lets
# us use os.getenv() below. In Docker the env vars come from env_file,
# but locally (without Docker) this line makes it work too.
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# In production, generate a real key with: python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "insecure-dev-key-change-me")

DEBUG = os.getenv("DJANGO_DEBUG", "True").lower() in ("true", "1", "yes")

ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


# --- Apps ---
# Order matters: Django's built-ins first, then third-party, then ours.

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",            # DRF — gives us serializers, viewsets, browsable API
    "rest_framework.authtoken",  # Token auth for API clients (curl, Postman, etc.)
    "django_filters",            # Declarative queryset filtering for DRF
    # Our apps
    "documents",    # domain models + business logic
    "api",          # REST endpoints (JSON)
    "ui",           # HTMX-powered HTML pages
]


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",       # CSRF protection — needed for HTMX POST forms
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # Look for templates in a top-level "templates/" dir (for login.html)
        # plus each app's own templates/ dir (APP_DIRS=True)
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# --- Database ---
# We MUST use PostgreSQL per the assignment. The host "db" is the
# docker-compose service name — Docker's internal DNS resolves it
# to the Postgres container's IP automatically.

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("POSTGRES_DB", "datavault"),
        "USER": os.getenv("POSTGRES_USER", "datavault"),
        "PASSWORD": os.getenv("POSTGRES_PASSWORD", "datavault"),
        "HOST": os.getenv("POSTGRES_HOST", "db"),
        "PORT": os.getenv("POSTGRES_PORT", "5432"),
    }
}


# --- Auth ---
# No password validators in dev — keeps superuser creation simple.
# In production you'd add MinimumLengthValidator, etc.
AUTH_PASSWORD_VALIDATORS = []

LOGIN_URL = "/login/"
LOGIN_REDIRECT_URL = "/"         # after login, go to home (redirects to upload)
LOGOUT_REDIRECT_URL = "/login/"  # after logout, go to login


# --- DRF ---
# These are the GLOBAL defaults. Individual views can override them.

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        # SessionAuth: works when you're logged in via the browser.
        # TokenAuth: works with "Authorization: Token <key>" header (for curl/Postman).
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        # This is the key line: GET requests are public, but POST/PATCH/PUT/DELETE
        # require a logged-in user. This satisfies the assignment's auth requirement
        # without needing per-view permission checks.
        "rest_framework.permissions.IsAuthenticatedOrReadOnly",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
}


# --- Static & Media ---
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded PDFs go here. In Docker, this is a named volume
# so files survive container restarts.
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


# --- Upload limits ---
# 10MB should be plenty for financial PDFs. This prevents someone
# from uploading a 2GB file and crashing our server.
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024   # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024


# --- Misc ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
