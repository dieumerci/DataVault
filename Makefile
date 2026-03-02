
.PHONY: build up down migrate superuser test shell logs restart

# Build the Docker image (re-run after changing Dockerfile or requirements.txt)
build:
	docker compose build

# Start both containers (Postgres + Django) in the background
up:
	docker compose up -d

# Stop all containers
down:
	docker compose down

# Run database migrations inside the web container
migrate:
	docker compose exec web python manage.py migrate

# Create an admin user for the web UI
superuser:
	docker compose exec web python manage.py createsuperuser

# Run the full test suite with verbose output
test:
	docker compose exec web python manage.py test --verbosity=2

# Open a Django Python shell (useful for debugging and data inspection)
shell:
	docker compose exec web python manage.py shell

# Tail the web server logs in real time (Ctrl+C to stop)
logs:
	docker compose logs -f web

# Restart the web container (picks up code and template changes)
restart:
	docker compose restart web
