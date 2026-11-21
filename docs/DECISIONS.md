# DECISIONS (ADRs)

## 2026-11-21: Monorepo layout and tooling
- Layout per AGRODESK_PROJECT.md Part F.2. Python 3.12 + FastAPI, ruff for lint/format, pytest.
- Docker Compose runs only Postgres (pgvector) and Redis; API runs on host during early dev.
- Web (Next.js), workers (Celery) and packages are placeholders until their epics start.
