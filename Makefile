.PHONY: up down test lint fmt
up:
	docker compose up -d
down:
	docker compose down
test:
	cd apps/api && python -m pytest -q
lint:
	cd apps/api && ruff check . && ruff format --check .
fmt:
	cd apps/api && ruff check --fix . && ruff format .
