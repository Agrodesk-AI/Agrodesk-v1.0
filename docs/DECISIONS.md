# DECISIONS (ADRs)

## 2026-11-21: Monorepo layout and tooling
- Layout per AGRODESK_PROJECT.md Part F.2. Python 3.12 + FastAPI, ruff for lint/format, pytest.
- Docker Compose runs only Postgres (pgvector) and Redis; API runs on host during early dev.
- Web (Next.js), workers (Celery) and packages are placeholders until their epics start.

## 2026-11-21: v1.0 MVP system design
- See docs/SYSTEM_DESIGN.md for the full doc.
- 12 numbered trade-offs recorded in §5 (monolith, shared DB+RLS, pgvector, REST+JSON, Postgres outbox, LangGraph, BSP adapter, hosted LLMs, PWA, voice outside LangGraph, no customer payments, single region).
- Assumptions 1-7 in §7 need validation during E0-E8.

## 2026-11-21: E1 auth + tenancy decisions (locked)
- **OTP:** 6 digits, 5-min TTL, max 3 requests/phone/hour, max 5 verify attempts, bcrypt-hashed in `otp_codes`.
- **Tokens:** JWT HS256, access 60 min, refresh 30 days (rotated on `/auth/refresh`).
- **Platform admin:** stored in `users` with `dealer_id IS NULL` and `role='platform_admin'`; DB check constraint enforces the shape.
- **Phone normalization:** E.164 with `IN` default. MVP in `app.security.phone`; swap for `phonenumbers` later.
- **RLS:** `ENABLE + FORCE ROW LEVEL SECURITY` on `users` and `dealers`. Policy gated by `app.current_dealer` and `app.is_platform_admin` session settings (set via `set_config(..., true)` inside the request transaction).
- **DB role:** application must connect as a **non-superuser** role (superuser bypasses even FORCE RLS). Alembic can run as either — the migration contains no tenant-scoped inserts.
- **RLS test outcome:** owner A attempting to GET/DELETE dealer B's user by ID returns **404** (not 403) so the ID is not an oracle. Platform admin sees both — proves the bypass works.
- **Ruff `B008` ignored:** FastAPI's `Depends(...)` default pattern is idiomatic and safe.
