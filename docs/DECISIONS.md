# DECISIONS (ADRs)

## 2026-11-21: Monorepo layout and tooling
- Layout per AGRODESK_PROJECT.md Part F.2. Python 3.12 + FastAPI, ruff for lint/format, pytest.
- Docker Compose runs only Postgres (pgvector) and Redis; API runs on host during early dev.
- Web (Next.js), workers (Celery) and packages are placeholders until their epics start.

## 2026-11-21: v1.0 MVP system design
- See docs/SYSTEM_DESIGN.md for the full doc.
- 12 numbered trade-offs recorded in §5 (monolith, shared DB+RLS, pgvector, REST+JSON, Postgres outbox, LangGraph, BSP adapter, hosted LLMs, PWA, voice outside LangGraph, no customer payments, single region).
- Assumptions 1-7 in §7 need validation during E0-E8.
