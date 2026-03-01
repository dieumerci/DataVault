# ──────────────────────────────────────────────────────────────
# Dockerfile for Data Vault
#
# We use a multi-step approach to keep the image small and builds fast:
#   1. Start from python:3.12-slim (not the full image)
#   2. Install system deps needed for PostgreSQL
#   3. Install Python packages (cached layer — only re-runs when
#      requirements.txt changes)
#   4. Copy our application code
# ──────────────────────────────────────────────────────────────

# We use python:3.12-slim instead of the full image.
# "slim" drops docs, man pages, and dev headers we don't need.
# This cuts the image from ~900MB to ~150MB.
FROM python:3.12-slim

# PYTHONDONTWRITEBYTECODE: don't create .pyc files in the container
#   (they're useless in Docker since the container is ephemeral)
# PYTHONUNBUFFERED: print output immediately to stdout
#   (important for docker logs — without this, logs get buffered and delayed)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system-level dependencies.
# psycopg2-binary usually works without system deps, but on slim images
# we still need libpq for the PostgreSQL client library at runtime.
# gcc is a safety net in case pip needs to compile anything from source.
# We clean up the apt cache afterward to keep the layer small.
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies FIRST, before copying our code.
# Docker caches each layer, so if requirements.txt hasn't changed,
# this layer is reused and we skip the slow pip install step.
# This is a standard Docker optimization for faster rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Now copy our actual application code.
# This layer changes frequently (every code edit), but because it's
# AFTER the pip install layer, we don't re-install packages on every build.
COPY . .

# Collect static files (CSS, JS) into STATIC_ROOT.
# The "|| true" means this won't fail if there's no database available
# yet during the build step (collectstatic doesn't need one, but some
# apps import models during startup which can trigger DB connections).
RUN python manage.py collectstatic --noinput 2>/dev/null || true

# Expose port 8000 for the web server
EXPOSE 8000

# Default command — docker-compose overrides this with its own command
# that includes migrations before starting gunicorn.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--timeout", "120", "--workers", "2", "--access-logfile", "-", "--reload"]
