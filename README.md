# Data Vault

**Document Intake & Field Correction Service** built with Django, PostgreSQL, and HTMX.

Upload financial documents (PDF or JSON), automatically extract key fields like routing numbers and amounts, then let operations users review and correct the extracted data through a clean web interface. Every correction is tracked — who changed what and when — so you always have a full audit trail.

Link to Video: https://drive.google.com/file/d/1u2ye9PQgXuFEXwS5anN1OXIawx3c9QP1/view?usp=sharing

---

## Tech Stack

| Layer       | Technology                              | Why I chose it                                       |
|-------------|-----------------------------------------|------------------------------------------------------|
| Backend     | Django 5.1.4, Django REST Framework     | Mature, batteries-included, great ORM for PostgreSQL |
| Database    | PostgreSQL 16                           | Required by the assignment; COALESCE and CAST support |
| Frontend    | HTMX 2.0.4, Tailwind CSS (CDN)         | Dynamic UI without writing JavaScript                |
| PDF Parsing | pypdf (pure Python)                     | No system deps, keeps Docker image small             |
| Server      | Gunicorn (production WSGI)              | Multi-worker, production-grade                       |
| Container   | Docker + Docker Compose                 | One command to spin up everything                    |

---

## Getting Started

There are two ways to run the app: **Docker** (recommended — one command, everything included) or **locally** (useful for faster iteration and debugging without containers).

---

### Option 1: Docker (Recommended)

Docker handles PostgreSQL, migrations, and the web server automatically. You don't need Python or PostgreSQL installed on your machine.

#### Prerequisites

- [Docker Desktop](https://docs.docker.com/get-docker/) (includes Docker Compose v2)
- Make (optional — provides shortcut commands)

#### Steps

```bash
# 1. Clone the repo and enter the project folder
git clone <repo-url>
cd Data-Vault

# 2. Create your environment file from the template
#    The defaults work out of the box — no edits needed.
cp .env.example .env

# 3. Build the Docker image and start both containers (Postgres + Django)
#    This also runs database migrations automatically on startup.
docker compose up --build -d

# 4. Create an admin user so you can log in to the web UI
docker compose exec web python manage.py createsuperuser
# Follow the prompts to set username, email, and password.
# For quick testing, use: admin / admin@test.com / admin

# 5. Open the app in your browser
open http://localhost:8000
# On Linux: xdg-open http://localhost:8000
```

#### Useful Docker Commands

```bash
# Start everything (after initial build)
docker compose up -d

# Stop all services
docker compose down

# Watch the server logs in real time
docker compose logs -f web


```

#### Makefile Shortcuts

If you have `make` installed, these save some typing:

| Command          | What it does                           |
|------------------|----------------------------------------|
| `make build`     | Build the Docker image                 |
| `make up`        | Start containers in background         |
| `make down`      | Stop all containers                    |
| `make migrate`   | Run database migrations                |
| `make superuser` | Create an admin user                   |
| `make test`      | Run the full test suite                |
| `make shell`     | Open Django Python shell               |
| `make logs`      | Tail the web server logs               |
| `make restart`   | Restart the web container              |

---

### Option 2: Running Locally (Without Docker)

Run Django directly on your machine. This gives you faster reload cycles and easier debugging with breakpoints. You'll need Python and PostgreSQL installed.

#### Prerequisites

- **Python 3.12+** — check with `python3 --version`
- **PostgreSQL 16** — running on your machine or a remote server
- **pip** — comes with Python (check with `pip3 --version`)
- **macOS only:** `brew install libpq` — the PostgreSQL client library. The app auto-detects it from Homebrew, no extra config needed. (Linux includes it with PostgreSQL; Docker doesn't need it.)

#### Step-by-step Setup

```bash
# 1. Clone the repo
git clone <repo-url>
cd Data-Vault

# 2. Create a virtual environment
#    This keeps the project's packages isolated from your system Python.
python3 -m venv venv

# 3. Activate the virtual environment
#    You'll see (venv) appear in your terminal prompt.
source venv/bin/activate
# On Windows: venv\Scripts\activate

# 4. Install all Python dependencies
#    This reads requirements.txt and installs Django, DRF, pypdf, etc.
pip install -r requirements.txt
```

#### Configure the environment

```bash
# 5. Create your environment file
cp .env.example .env
```

Now open `.env` in your editor and change `POSTGRES_HOST` from `db` to `localhost`:

```env
# The only change you need for local development:
# "db" is Docker's internal hostname — locally, Postgres runs on localhost.
POSTGRES_HOST=localhost
```

All other defaults (`datavault` for db name, user, and password) work as-is.

#### Set up the database

```bash
# 6. Create the PostgreSQL database
#    Option A: using the createdb command (if available)
createdb datavault

#    Option B: using psql directly
psql -U postgres -c "CREATE DATABASE datavault;"

#    Option C: if your Postgres uses a different user
psql -c "CREATE USER datavault WITH PASSWORD 'datavault';"
psql -c "CREATE DATABASE datavault OWNER datavault;"

# 7. Run Django migrations to create all the tables
python manage.py migrate
```

#### Create an admin user

```bash
# 8. Create a superuser so you can log in to the web UI
python manage.py createsuperuser
# Follow the prompts to set username, email, and password.
# For quick testing, use: admin / admin@test.com / admin
```

#### Start the development server

```bash
# 9. Run the app
python manage.py runserver

# The app is now at http://localhost:8000
# Log in with the admin credentials you just created.
```

#### Running Tests Locally

```bash
# Run all tests with verbose output
python manage.py test --verbosity=2

# Run just the domain layer tests
python manage.py test documents --verbosity=2

# Run just the API tests
python manage.py test api --verbosity=2
```

---

## What's in `requirements.txt`

Every dependency is explained in the file itself, but here's the quick version:

| Package                | What it does                                            |
|------------------------|---------------------------------------------------------|
| `Django`               | Web framework — routing, ORM, templates, auth           |
| `djangorestframework`  | Adds REST API layer (serializers, views, token auth)    |
| `django-filter`        | Declarative search filters for DRF                      |
| `psycopg2-binary`      | PostgreSQL driver (pre-compiled, no C compiler needed)  |
| `pypdf`                | PDF text extraction (pure Python, no system deps)       |
| `python-dotenv`        | Reads `.env` files into environment variables           |
| `gunicorn`             | Production WSGI server (used in Docker)                 |

---

## Pages

| URL                    | What it does                                      |
|------------------------|---------------------------------------------------|
| `/login/`              | Login page — use the admin credentials you created |
| `/upload/`             | Upload a PDF or paste JSON to create a document    |
| `/documents/<uuid>/`   | View extracted fields + correct them inline        |
| `/search/`             | Search and filter across all documents             |
| `/admin/`              | Django admin panel (for debugging)                 |

## API Endpoints

| Method | URL                             | Auth Required | Description                     |
|--------|---------------------------------|---------------|---------------------------------|
| GET    | `/api/documents/`               | No            | List and search documents       |
| POST   | `/api/documents/`               | Yes           | Create via PDF upload or JSON   |
| GET    | `/api/documents/<uuid>/`        | No            | Single document with all fields |
| PATCH  | `/api/fields/<id>/`             | Yes           | Correct a field value           |
| GET    | `/api/reports/top-corrections/` | No            | Most frequently corrected fields |

## API Examples

### Upload a PDF

```bash
curl -X POST http://localhost:8000/api/documents/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -F "file=@document.pdf" \
  -F "form_type=w9"
```

### Submit JSON fields

```bash
curl -X POST http://localhost:8000/api/documents/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "form_type": "ach_authorization",
    "fields": [
      {"key": "routing_number", "value": "021000021", "data_type": "string"},
      {"key": "amount", "value": "1500.00", "data_type": "number"},
      {"key": "customer_name", "value": "Jane Smith", "data_type": "string"}
    ]
  }'
```

### Search documents

```bash
# By form type
curl "http://localhost:8000/api/documents/?form_type=w9"

# By field value (searches the corrected value if one exists)
curl "http://localhost:8000/api/documents/?field_key=customer_name&field_value=Jane"

# By amount range
curl "http://localhost:8000/api/documents/?amount_min=100&amount_max=5000"
```

### Correct a field

```bash
curl -X PATCH http://localhost:8000/api/fields/1/ \
  -H "Authorization: Token YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"corrected_value": "021000089"}'
```

### Top corrections report

```bash
curl "http://localhost:8000/api/reports/top-corrections/?limit=5"
```

### Getting an API Token

```bash
# Via Django shell (works with both Docker and local):
python manage.py shell -c "
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
user = User.objects.get(username='admin')
token, _ = Token.objects.get_or_create(user=user)
print(token.key)
"

# In Docker, prefix with: docker compose exec web
```

---

## Running Tests

```bash
# Docker
docker compose exec web python manage.py test --verbosity=2
# or: make test

# Local
python manage.py test --verbosity=2
```

The test suite covers: effective value logic, field extraction, JSON ingestion, PDF validation, auth enforcement, search with corrections, and the reporting query.

---

## Project Structure

```
Data-Vault/
├── config/                     # Django project settings and configuration
│   ├── settings.py             # All config via environment variables
│   ├── urls.py                 # Root URL routing: /api/, /admin/, / (ui)
│   └── wsgi.py                 # WSGI entry point for gunicorn
│
├── documents/                  # Domain layer — the core of the application
│   ├── models.py               # Document + Field models (effective_value lives here)
│   ├── tests.py                # Unit tests for models and services
│   └── services/               # Pure Python business logic (no HTTP awareness)
│       ├── extraction.py       # PDF text extraction + regex field parsers
│       ├── ingestion.py        # Orchestrates document creation (PDF + JSON paths)
│       ├── search.py           # Filtered queries using COALESCE for corrections
│       └── reporting.py        # Raw SQL query for top-corrections report
│
├── api/                        # REST API layer (Django REST Framework)
│   ├── serializers.py          # Model-to-JSON translation (3 serializers)
│   ├── views.py                # Thin HTTP wrappers around service functions
│   ├── urls.py                 # API route definitions
│   └── tests.py                # Integration tests (auth, search, reporting)
│
├── ui/                         # Web interface (server-rendered HTML + HTMX)
│   ├── views.py                # Upload, detail, correction, search views
│   ├── urls.py                 # Page routes + Django auth views
│   └── templates/ui/
│       ├── base.html           # Layout with Tailwind CSS + HTMX loaded
│       ├── upload.html         # PDF upload + JSON textarea forms
│       ├── document_detail.html # Fields table with inline HTMX editing
│       ├── search.html         # Dynamic search with 7 filter inputs
│       └── partials/           # HTMX fragment templates
│           ├── field_row.html  # Single table row — the HTMX swap target
│           └── search_results.html  # Results table (swapped on filter change)
│
├── templates/registration/
│   └── login.html              # Login page using Django's built-in auth
│
├── docker-compose.yml          # Two services: PostgreSQL + Django/Gunicorn
├── Dockerfile                  # Python 3.12-slim image with all dependencies
├── Makefile                    # Shortcut commands (make test, make up, etc.)
├── requirements.txt            # Pinned Python dependencies with explanations
├── .env.example                # Template for environment variables
├── SOLUTION.md                 # Architecture decisions, trade-offs, and video presentation guide
└── README.md                   # This file
```
