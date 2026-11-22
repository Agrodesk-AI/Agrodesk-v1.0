.PHONY: up down db-roles migrate migrate-test test lint fmt

# Owner role (superuser) — DDL/migrations only.
OWNER_DB ?= postgresql+asyncpg://agrodesk:agrodesk@localhost:5433
# App role (NOSUPERUSER NOBYPASSRLS) — API, workers, tests. RLS only holds for this role.
APP_DB ?= postgresql+asyncpg://agrodesk_app:agrodesk_app@localhost:5433

up:
	docker compose up -d
down:
	docker compose down
# Create/refresh the agrodesk_app role + grants on an existing volume (new volumes get it on init).
db-roles:
	docker compose exec -T db bash -s < infra/postgres/initdb/10-app-role.sh
migrate:
	cd apps/api && MIGRATIONS_DATABASE_URL=$(OWNER_DB)/agrodesk alembic upgrade head
migrate-test:
	cd apps/api && MIGRATIONS_DATABASE_URL=$(OWNER_DB)/agrodesk_test alembic upgrade head
# Tests always connect as the app role; a superuser would silently skip RLS.
test:
	cd apps/api && TEST_DATABASE_URL=$(APP_DB)/agrodesk_test python -m pytest -q
lint:
	cd apps/api && ruff check . && ruff format --check .
fmt:
	cd apps/api && ruff check --fix . && ruff format .
