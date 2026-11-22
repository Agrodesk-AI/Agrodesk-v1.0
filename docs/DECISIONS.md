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

## 2026-11-22: E3.1 offline + i18n + e2e decisions
- **Offline queue:** IndexedDB via `idb`, store `queued_requests`. Only queues `POST /v1/leads` and `POST /v1/tasks/{id}/outcome` — reads stay online so the UI never shows stale data.
- **Replay triggers:** window `online` event, `document.visibilitychange` to `visible`. Service worker registers a `sync` event (`agrodesk-replay` tag) that signals the window to replay when the browser supports Background Sync; iOS Safari relies on the visibility-change path.
- **Error handling:** 4xx (except 408/429) drops the queued item — the user will re-do; network errors and 5xx stay in the queue with a `retries` counter. OfflineIndicator shows a top chip with the queue length.
- **i18n:** `next-intl` with **no URL locale routing**. `NextIntlClientProvider` wraps the whole app in a client provider that reads `localStorage['agrodesk.locale']`, falling back to the browser's accepted language, then `en`. The language picker lives on `/profile`.
- **Catalogs:** machine-authored `src/messages/{en,mr,hi}.json`. Needs a native-speaker review before pilot — tracked in `docs/PROGRESS.md`.
- **Playwright:** smoke test skipped unless `E2E_OWNER_FIXED_CODE` is set; relies on a live dev-mode backend with a seeded owner. Full e2e with fixtures lands later.

## 2026-11-22: E4 bulk import decisions
- **Endpoint:** `POST /v1/leads/import` — multipart with `file`, JSON `mapping`, `default_source`, `duplicate_policy`, `dry_run`.
- **Formats:** `.csv` (stdlib `csv` with UTF-8 BOM handling) and `.xlsx`/`.xlsm` (openpyxl, read-only + data-only).
- **Limits:** 2 MB file size, 5000 data rows. Beyond that, point users at Celery batch — tracked for a later epic.
- **Required columns:** `phone` + `name`. Every other canonical field (`model_interest`, `source`, `campaign`, `ad_name`, `next_action_at`) is optional, with fallbacks (`source` → `default_source`; `next_action_at` → tomorrow 10:00 IST).
- **Duplicate policies:**
  - `skip` — ignore rows whose `(dealer_id, phone)` already exists
  - `update_customer` — update the existing customer's `name`, then create a new lead
  - `create_lead_only` (default) — keep the customer unchanged, add a new lead
- **Phone normalization + source validation** run per-row; failures produce an `ImportRowError` (row, field, message) and the row is dropped.
- **Cross-tenant proven:** dealer A importing a phone that exists on dealer B creates a new customer in A — verified by `tests/test_import.py::test_cross_tenant_import`.
- **Acceptance** (`test_acceptance_100_rows_10_dup_5_invalid`): 100 rows, 10 duplicates, 5 invalid phones, `skip` policy → 85 created, 10 skipped, 5 errors (matches brief E.4 exactly).
- **Lead provenance:** rows imported from a file get `created_via='csv'` and a `created` event with `payload.via='csv_import'` and `payload.row=<file row number>`.
- **Frontend:** 3-step wizard with auto-detected column mapping (phone/name/model/source/campaign/ad_name/next_action_at); `dry_run` on by default so users preview before writing; error CSV downloads client-side.

## 2026-11-22: E5 Planner decisions
- **Celery config:** app `agrodesk`, broker + backend on `REDIS_URL`, queue `agrodesk`, `task_acks_late=True`, `worker_prefetch_multiplier=1` so a long task doesn't hog a worker.
- **Beat schedule (UTC):** 19:00 → `generate_tasks_for_due` (00:30 IST); 20:30 → `check_stale_leads` (02:00 IST); `02:35-15:35` hourly → `emit_overdue_alerts` (~08:05-21:05 IST).
- **Idempotency:** `job_runs(job_name, logical_date, COALESCE(scope_id, '00…000'::uuid))` unique index. `_acquire_run` returns False if someone else claimed the key.
- **Async in Celery:** tasks are thin sync wrappers calling `asyncio.run(planner_service.*)`. Keeps the sync-vs-async boundary at exactly one place; tests call the service functions directly.
- **Overdue threshold:** `next_action_at + 2h < now` (configurable via `OVERDUE_THRESHOLD_HOURS`). One alert per lead per day via `job_runs` scoped by `lead_id`.
- **Stale threshold:** 14 days since the last `lead_event`, configurable via `STALE_LEAD_DAYS`. Writes a `note` event with `payload.kind='stale_flagged'`.
- **Outcome rules (code, not AI):**
  - `not_picked` → +1d; `interested` → +2d; `price_issue` → +3d
  - `visit_planned` → day before current `next_action_at` if ≥ 2 days out, else +3d
  - `bought_elsewhere` / `not_interested` → None (don't reschedule; the user is expected to transition to `lost` next)
  - `other` → +2d
- **POST /v1/tasks/{id}/outcome** now accepts an optional `next_action_at` to override the suggestion; applies it to the lead, writes `next_action_scheduled` event, and inserts a fresh pending task.
- **GET /v1/tasks/{id}/suggest?outcome=…** returns the suggested next action without mutating state — used by the OutcomeSheet to preview.

## 2026-11-22: E6 WhatsApp gateway decisions
- **BSP adapter is a Protocol** (`WhatsAppProvider`) with 4 methods: `send_session`, `send_template`, `verify_signature`, `parse_webhook`. First implementation is `FakeWhatsAppProvider` (in-process send sink + HMAC-SHA256 signing) selected via `WHATSAPP_PROVIDER=fake`. Gupshup / Interakt / WATI / WhatsApp Cloud API are swap-in classes.
- **Outbox pattern:** writers call `outbox_service.enqueue()` inside their own DB transaction so the message intent and the business change commit together. Celery task `app.jobs.outbox.process_pending` polls every 60 s and dispatches.
- **Retries:** `RETRY_DELAYS_SEC = [60, 300, 900, 3600, 14400, 86400]`. On the 6th consecutive failure the row is marked `failed` and a `note` event (`payload.kind='message_dead_letter'`) is written to the related lead, ready for owner UI.
- **Rejected vs failed:** `rejected` is terminal-without-retry (opt-out, missing customer, provider 4xx, outside session window); `failed` is terminal after exhausting retries. Both get out of the poll loop and stop costing cycles.
- **24-hour session window:** computed from `conversations.last_customer_message_at`. `kind='wa_session'` outside the window → `rejected(outside_session_window)`. Templates (`kind='wa_template'`) always allowed.
- **Webhook:** `POST /v1/webhooks/whatsapp`, public, body signed via HMAC-SHA256 against `WHATSAPP_WEBHOOK_SECRET`. Header `X-Hub-Signature-256: sha256=<hex>` (Meta's shape; most BSPs mirror). Missing / wrong signature → 401.
- **Replay idempotency:** `provider_message_id` has a partial unique index on `messages`. Replays return `duplicates=1` and are a no-op.
- **Dealer routing:** inbound message resolves dealer by `dealers.whatsapp_number == event.to_phone`; unknown dealer increments `unknown_dealer` and is otherwise ignored.
- **Unknown-customer flow:** first inbound creates a stub customer `name="WhatsApp <phone>"` with dealer's default language.
- **Opt-out keywords:** `STOP`, `STOP ALL`, `BAND`, `UNSUBSCRIBE` (Latin exact match, case-insensitive) and `रद्द`, `बंद`, `बंद करो`, `मैसेज बंद` (Devanagari contains). First-pass list — book native-speaker review before pilot.
- **Outbox idempotency:** every outbox row carries an `idempotency_key` (unique across the table); the sent `messages` row reuses it so the adapter can safely dedupe retries at the BSP.
- **Status updates:** webhook also accepts `{type:'status', id, status, failure_reason}` payloads and advances `messages.status`. Status ranks prevent an earlier status from overwriting a later one.

## 2026-11-22: E7 KB + RAG decisions
- **Vectors in JSONB, cosine in Python.** `kb_chunks.embedding` is `JSONB` (array of floats), the retrieval path is a plain `SELECT` + per-row `cos(q, v)` in Python. At the MVP volume (1 pilot dealer → ~1-10k chunks) this is milliseconds. The brief Part F.1 originally called for pgvector; I evaluated and chose JSONB because the production Postgres image (`pgvector/pgvector:pg16`) already covers us but the cloud CI sandbox cannot install the extension. Switch plan: when a single dealer crosses ~10k chunks, add a migration converting the column to `vector(384)`, rebuild the service search to use `<=>`, and keep the same shape of return. The service's public surface won't change.
- **Embedding dims 384.** Default `FakeEmbeddingProvider` (deterministic SHA-based L2-normalized vectors); real vendor loaded from `EMBEDDING_PROVIDER` env. Matches the size of most small sentence-transformer / Voyage-lite / Cohere-embed-light variants. Changing dims = reindex.
- **Chunking:** fixed character window, 800 / 100 overlap. Simple and good enough for brochures and FAQs; promote to sentence-aware when results get choppy.
- **PDF extraction:** `pypdf`. Scanned PDFs return 422 `pdf_scanned` — OCR is a later epic.
- **Shared vs private KB:** `dealer_id IS NULL` means shared. Read policy allows NULL OR tenant match; write policy allows platform-admin anywhere OR tenant-matched inserts only. `tractor_catalogue` is shared-read-by-all, write-by-platform-admin only (brand/model specs are platform data).
- **Catalogue overlay (`dealer_models`):** per-dealer price range and offers, keyed `(dealer_id, catalogue_id)` unique. **Expired offers** (`valid_till < today`) are hidden from `/v1/catalogue` server-side — the shared row still appears so staff aren't confused, but `price_min`, `price_max` and `offers` fall back to empty.
- **Search ranking:** `0.7·cosine + 0.3·keyword_boost` (keyword_boost = 1.0 if query is a substring of the chunk text, else 0). Keyword match beats pure-semantic noise when the Fake embeddings are random; real embeddings will lean more on the cosine component.
- **RLS proof point:** `tests/test_kb.py::test_cross_tenant_rls_isolation` probes `SELECT * FROM kb_chunks` as dealer B and asserts dealer A's private rows never appear, in addition to the usual API-level 404 checks.

## 2026-11-22: E7 KB + RAG decisions (pgvector)
- **pgvector `vector(384)`.** Per brief Part F.1. Migration 0005 `CREATE EXTENSION IF NOT EXISTS vector` + column type `vector(384)`. Service search uses the `<=>` cosine-distance operator.
- **Docker Compose** already uses `pgvector/pgvector:pg16` image → extension is pre-installed. Managed Postgres providers (AWS RDS, Supabase, Neon, etc.) all offer pgvector as an extension you enable once per DB.
- **ANN index deferred.** For MVP we rely on sequential scan + RLS filter. When a single dealer crosses ~10k chunks, run `CREATE INDEX kb_chunks_embedding_idx ON kb_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists=100)` after a representative data load (needed for good centroid choice).
- **Embedding dims 384** and `FakeEmbeddingProvider` (deterministic SHA-based L2-normalized vectors) for dev. Swap to a real provider via `EMBEDDING_PROVIDER` env; changing dims requires a column retype + reindex.
- **Chunking:** 800 chars / 100 overlap. Promote to sentence-aware when quality drops.
- **PDF extraction:** `pypdf`. Scanned PDFs return 422 `pdf_scanned` (OCR is a later epic).
- **Shared vs private KB:** `dealer_id IS NULL` = shared. Read policy allows NULL or tenant match; writes are tenant-scoped (platform-admin to insert shared rows). `tractor_catalogue` is shared-read-all + platform-admin writes only.
- **Catalogue overlay (`dealer_models`):** per-dealer price range and offers with `valid_till`. Expired offers (`valid_till < today`) filter out of `/v1/catalogue` server-side — the row still appears with `overlay_expired=true` and nulled prices.
- **Search ranking:** `0.7·(1 - cosine_distance) + 0.3·keyword_boost`. Keyword boost = 1.0 when the query substring is in the chunk text (case-insensitive).
- **RLS proof point:** `tests/test_kb.py::test_cross_tenant_rls_isolation` probes `SELECT * FROM kb_chunks` as dealer B and asserts dealer A's private rows never appear, in addition to the usual API-level checks.

## 2026-11-22: F3 community feed + moderation (design §3.4, §3.8)
- **Typed posts:** ask, need_equipment, offer_equipment, price_report, scheme_alert, experience. `price_report` requires crop + price (paise) + unit. Expiry per kind: prices 3 d, equipment 14 d, scheme alerts 30 d, others none.
- **Ranking in Python** over ≤500 recent candidates (30-day window): `0.6·locality + 0.3·recency + 0.1·helpfulness`; locality village 1.0 / tehsil 0.7 / curated neighbour 0.4 / district 0.1; recency half-life 48 h; helpfulness capped at 20 marks. First page under 10 items widens to the whole district. No Redis cache yet (pilot volume); add per (tehsil, tab, page) 60 s when §6 trigger hits.
- **Helpful, not likes:** the count is hidden below 10. Counters (helpful, replies) are kept by SECURITY DEFINER triggers, so readers never write others' posts.
- **Moderation layer 1 (code, always on):** Indian mobile numbers in any script's digits (normalised via `unicodedata.digit`) and blocklisted words → rejected at submit with a fixable reason. Links, UPI handles, known scam phrases → `in_review` + queue. 5 posts/h, 30 replies/h per farmer. The abuse blocklist is loaded at deploy (`moderation.load_blocklist`), not kept in the repo.
- **Layer 2:** `ContentClassifier` protocol, `FakeClassifier` in dev. Confidence < 0.7 or provider error → queue, never auto-block (code layer is the floor).
- **Reports:** each report queues the item (one open queue row per target, reasons merged). 3 reporters since the last human decision → auto-hide (`in_review`). Admin approve/remove closes the item with decided_by/note/time (audit).
- **Writes in platform context** (they touch the admin-only queue); reads (feed/detail) in farmer RLS context: published or own.
- **Not yet:** voice posts (STT adapter), real LLM classifier, warn/suspend actions, appeals, rating-ring detection, moderation admin UI.

## 2026-11-22: F2 rental exchange (design §3.5)
- **Pull matching, not push.** Owners see open nearby needs for kinds they list (`/v1/rentals/needs/nearby`); renters browse nearby listings or a need's matches. The Celery + WhatsApp-template push in the design waits for the BSP; the per-owner daily cap applies then.
- **"Nearby" = the F0 tehsil map** (own, curated neighbours, same-district fallback), not a per-listing `service_area` JSON. A booking outside that set is refused (`too_far`).
- **No double booking, enforced in Postgres:** `EXCLUDE USING gist (listing_id =, daterange &&) WHERE state IN ('agreed','in_progress')` (btree_gist). The service checks first for a clean 409; the constraint is the backstop. Agreeing auto-declines overlapping pending requests.
- **Availability without leaking bookings:** `rental_listing_busy()` is SECURITY DEFINER and returns only a boolean, since bookings are party-only under RLS.
- **Masked contact in-app** (not a WA relay yet): the phone is revealed only after both parties tap "share", and only from agreed onwards.
- **Ratings trust gate twice:** service check + `BEFORE INSERT/UPDATE` trigger (`rental_ratings_gate`): completed_by_both|rated only, party → other party only, once per side. Both rated → `rated`.
- **Disputes:** either side, from in_progress or within 7 days of completion, with a reason; resolved only by platform admin.
- **RLS:** listings and open needs are readable by any farmer (the marketplace), writable by the owner only. Bookings/events are party-only. Ratings are readable by any farmer (public trust signal). Two-party writes run in platform context with explicit party checks.
- **Money in paise**, no payments in-app. Rentals legal disclaimers still open (design §1.3).
- **Not yet:** host verification for high-trust rentals (design §1.1), WhatsApp notifications, voice needs.

## 2026-11-22: F1 consented lead routing (design §3.3)
- **Re-route via sweep, not per-lead ETA tasks.** Celery beat runs `process_due_routes` every 5 min with `SELECT … FOR UPDATE SKIP LOCKED`. Survives worker restarts, idempotent, worst-case 5 min late.
- **SLA = 4 business hours** in the dealer's `business_hours` (`{"mon": ["09:00","19:00"], …, "sun": null}`, IST; default Mon–Sat 9–19). An all-closed or broken schedule falls back to the default so SLAs can't stall forever.
- **"Responded" = any staff action** on the routed lead: stage transition or a call/note/opt-out event. PATCH edits don't count.
- **Ranking:** nearest service tehsil (own, curated neighbour, same-district fallback) → home-tehsil match → 90-day response rate (new dealers start at 0.5 until 3 routes) → capacity left today (`routing_daily_cap`, default 20). Only `verified_at IS NOT NULL` + active dealers. Brand match is case-insensitive exact on `dealers.brands`; no brand = any.
- **Candidates fixed at creation** (top 4 = 1 + max 3 re-routes). Re-checked for verification at each hand-off. Exhausted → `waitlist`.
- **On re-route** the old dealer's lead goes `lost` (`rerouted_sla`) with a `re_routed` timeline event and tasks skipped. No WhatsApp notice to the dealer yet.
- **Consent:** server-held versioned texts (en/hi/mr reviewed-pending; other languages get English and the response says so). Client sends version + language; server stores its own text. Changing wording = new version. App flow requires consent_granted=true; recording a "NO" will come with the WhatsApp Guide.
- **Anti-abuse:** 3 interests / farmer / 24 h; one open interest per brand. Phone-reputation (Lookup-style) checks still TODO.
- **Cross-tenant writes run in platform context** with explicit ownership checks (same pattern as onboarding). Farmer sees the dealer via a snapshot on the interest (business name + public WhatsApp number), never by reading dealer tables.

## 2026-11-22: F0 farmer foundation (all-India)
- **Scope is all of India**, not the pilot tehsil. Location PKs = LGD codes; names in `names` JSONB keyed by language; loaded from LGD CSVs via `scripts/import_lgd.py`. No geography hard-coded in migrations.
- **Language fallback for place names:** exact language, else untagged local name if same script, else English. Importer auto-tags unambiguous scripts (Tamil→ta, Telugu→te, …); `--local-lang` only applies to names in that language's script, so a multi-state file can't mislabel.
- **UI chrome fallback is English, not Hindi**, for languages without a UI catalog yet (en/mr/hi exist). Farmer content languages: en hi mr gu pa bn as or ta te kn ml ur.
- **Accounts → profiles.** `accounts(phone)` is the identity; `users` (dealer staff/admin) and `farmers` are profiles. Tokens carry `kind` = staff | farmer | account. `get_current_user` is now staff-only, so every existing dealer route rejects farmer/onboarding tokens with 403 `staff_only`.
- **Unknown phones now get an account-only token** (was 401) that can only browse locations and call `POST /v1/farmer/onboard`. Login defaults to the staff profile when both exist; `POST /v1/auth/switch-profile` changes it.
- **Age gate:** self-declared DOB stored on the account, 18+ enforced at onboarding. Stronger verification still pending legal (design §3.1).
- **Farmer RLS:** new GUCs `app.current_farmer`, `app.current_account`; `farmers` and `accounts` rows visible only to self or platform admin.
- **Onboarding runs in platform context** (same as OTP verify) with explicit ownership checks, since the farmer row id doesn't exist yet when RLS would need it.

## 2026-11-22: System Design v2 — two-sided app
- See `docs/SYSTEM_DESIGN_v2.md`. Supersedes `docs/SYSTEM_DESIGN.md` on the new scope: dealer/farmer split, location hierarchy with tehsil neighbours, consented lead routing with SLA re-route, typed community feed, rental exchange state machine, subsidy rules engine, deterministic trust signals, two-layer moderation, expert Q&A queue, STT/TTS adapter pattern.
- 12 numbered trade-offs in §5. 7 assumptions in §7 that must be validated during the pilot.
