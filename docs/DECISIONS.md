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

## 2026-11-22: E2 customers + leads decisions
- **Customer dedup:** `POST /customers` returns existing row with 200 on `(dealer_id, phone)` collision (no name/field merge — PATCH does that).
- **Phone uniqueness:** `customers(dealer_id, phone)` unique — same phone can exist across dealers.
- **State machine:** allowed transitions codified in `lead_service.ALLOWED_TRANSITIONS`. Won is terminal. Lost is reopenable via `new`. Any open stage requires `next_action_at`. DB CHECKs enforce `lost ⇒ lost_reason` and `won ⇒ won_at`.
- **Auto-tasks:** creating a lead or updating `next_action_at` upserts one `pending` task for `owner_user_id`. Full Planner (nightly beat) lands in E5.
- **Won/lost cancels pending tasks** (`status=skipped, completed_at=now`).
- **Events:** append-only `lead_events`; types are `created | stage_changed | assigned | next_action_scheduled | note | call_made | task_completed | opted_out`. Payload is jsonb.
- **List sort:** `next_action_at ASC NULLS LAST, created_at DESC`. Limit default 50, max 200.
- **No per-staff visibility restriction yet:** any authenticated user in a dealer sees all its leads. Sharpening comes with E5/E8.

## 2026-11-22: E3 web stack decisions
- **Framework:** Next.js 15 App Router, React 19, TS strict. PWA via manifest + `/sw.js` (empty cache now; offline queue in E3.1).
- **Styling:** Tailwind + custom tokens (primary `#1F4D2B` = deep green per brief Part I.6). shadcn-compatible stubs ship in `src/components/ui/*` so the app runs before anyone runs `shadcn add`; `components.json` is configured so `shadcn add` overwrites them cleanly.
- **State:** TanStack Query declared in deps for future use; E3 uses plain `useEffect`/`useState` for simplicity (Quick Add, list, detail are each 1-2 fetches).
- **Forms:** plain `useState` + inline validation. react-hook-form + zod reserved for larger forms (bulk-import wizard, settings).
- **Token storage:** access in `localStorage`, refresh in `localStorage` (not httpOnly cookie — deferred; will revisit when we add a Next.js server-side API proxy that holds sessions).
- **API client:** `src/lib/api.ts` handles JWT + auto-refresh on 401. Base URL `/api/backend` — Next rewrites to `API_URL` so there's no CORS in dev.
- **Icons:** `lucide-react`.
- **Shell:** bottom tab bar (mobile) with FAB-style `+` for Quick Add; sidebar (md+).
- **Deferred to E3.1:** offline queue via service worker + IndexedDB, next-intl Marathi/Hindi catalogs, Playwright e2e tests, Android push.
