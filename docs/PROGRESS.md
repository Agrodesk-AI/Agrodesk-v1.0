# PROGRESS

## Status (2026-11-21)
- Epic E0 scaffold created: monorepo layout, docker-compose (Postgres 16 + pgvector, Redis), Makefile, CI, API health endpoint + test.
- Verified (Python 3.13, cloud workspace): ruff lint + format clean, pytest 1 passed.
- Not verified: `make up` (Docker not available in the Cowork VM; run on your Windows machine with Docker Desktop).

## Done
- F3 community feed: migration 0009 (posts, post_replies, post_helpful, content_reports, moderation_queue; counter triggers), two-layer moderation (`services/moderation.py`: script-agnostic phone block, link/UPI/scam flags, loadable blocklist, classifier protocol + Fake), locality-first ranking with district widening, reports with auto-hide at 3, admin queue + decide. PWA: Community tab (6 tabs, post cards with price display, helpful, report sheet), compose with price fields and blocked/in-review messaging, post detail with replies. 120 backend tests pass; web typecheck clean; post/blocked-phone/price/reply flow checked in browser.
- F2 rental exchange: migration 0008 (equipment_listings, rental_needs, rental_bookings with exclusion constraint, rental_booking_events, rental_ratings + trigger gate, rental_listing_busy fn), rental_service (nearby browse, needs, state machine, masked contact, ratings, admin resolve), `/v1/rentals/*` + `/v1/admin/rentals/bookings/{id}/resolve`. PWA: Rent tab (browse + request, post a need), My equipment (listings + nearby needs), booking page (actions, share contact, rate, history). 97 backend tests pass; web typecheck clean; owner/renter flow checked in browser through contact unmasking.
- F1 consented lead routing: migration 0007 (dealer verification + daily cap, farmer_consents, buying_interests, lead_routes, `agrodesk_guide` source, routed/re_routed/farmer_cancelled events), routing_service (ranking, business-hours SLA, sweep re-route, cancel), Celery beat every 5 min, APIs `/v1/farmer/interests*`, `/v1/dealer/service-areas`, `/v1/admin/dealers/{id}/verify|unverify`. PWA: `/farm/buy` with consent text, requests on farm home (call/WhatsApp/cancel), dealer lead list "Agrodesk Guide · Respond by". 88 backend tests pass; web typecheck clean; full flow checked in browser (Marathi farmer → Niphad dealer).
- F0 farmer foundation (all-India): migration 0006 (states/districts/tehsils/villages keyed by LGD code, tehsil_neighbours, dealer_service_areas, accounts, farmers + RLS), LGD CSV importer `scripts/import_lgd.py`, account→profiles auth (staff | farmer | account tokens, switch-profile, profiles list), `/v1/farmer/onboard|me`, `/v1/locations/*` incl. nearby with same-district fallback, admin neighbour edit. PWA: `/onboarding` (13 languages, state→district→tehsil→village picker), `/farm` home + profile, profile switcher on both sides. 75 backend tests pass (run as a non-superuser role); web typecheck + build clean; flow checked in browser (Tamil farmer onboarding).
- E7 shipped: Knowledge base + catalogue — chunk + embed + hybrid search (Python cosine over JSONB vectors), shared/dealer scoping via RLS, expired-offer filter. 70/70 backend tests green.
- E6 shipped: WhatsApp gateway — conversations, messages, outbox with RLS; BSP adapter interface + Fake impl; signed webhook with replay guard; outbox worker with 1m→5m→15m→1h→4h→24h retry schedule and dead-letter. 59/59 backend tests green.
- E5 shipped: Planner with Celery beat (generate_tasks_for_due nightly, check_stale_leads daily, emit_overdue_alerts hourly), suggested-next-date rules, outcome reschedules lead + task. 46/46 backend tests green.
- E4 shipped: POST /v1/leads/import (CSV + XLSX) with per-row validation, duplicate policies, dry-run, and error report. Frontend 3-step wizard at /leads/import. 38/38 backend tests green.
- E3.1 shipped: offline write queue (IndexedDB) + next-intl en/mr/hi catalogs + Playwright smoke test scaffold. Build passes, typecheck clean, 7 routes.
- E3 shipped: Next.js 15 PWA shell + auth + Today's Tasks + Leads list + Quick Add + Lead detail with timeline + transitions.
- E2 shipped: customers + leads core API with state machine + event log (27/27 tests pass).
- E1 shipped: auth, tenancy with RLS, cross-tenant test green.
- docs/SYSTEM_DESIGN.md written — MVP architecture, data flow, trade-offs, scale plan, assumptions.

## Next
- **Security: run the API as a non-superuser Postgres role.** Superusers bypass RLS even with FORCE. With the default `agrodesk` superuser, 4 cross-tenant tests fail (dealer A can read dealer B's leads/users). Create a `NOSUPERUSER NOBYPASSRLS` app role, grant table privileges, point `DATABASE_URL` at it; keep the owner role only for migrations. Tests should run as that role too: `TEST_DATABASE_URL=postgresql+asyncpg://agrodesk_app:...@localhost:5433/agrodesk_test`.
- Pre-existing: 4 `tests/test_kb.py` tests fail with `TypeError: float * decimal.Decimal` in KB search on this machine. Unrelated to F0; needs a look.
- Load real LGD data: download state/district/sub-district CSVs (all India) and village CSVs per state from lgdirectory.gov.in, run `scripts/import_lgd.py` top-down. Verify the header aliases against the current export format on the first run.
- Curate `tehsil_neighbours` for the pilot district first (CSV `tehsil_code,neighbour_code,rank`); every other tehsil uses the same-district fallback until curated.
- UI catalogs exist only for en/mr/hi; other farmer languages get English chrome with native place names. Add catalogs (gu, pa, bn, ta, te, kn, ml, or, as, ur) with native-speaker review.
- New mr/hi strings (onboarding, farm, profiles, location) are machine-authored — include in the native-speaker pass.
- Dealer service areas: API done (`PUT /v1/dealer/service-areas`, owner only); no dealer UI yet. Admin verify has no UI either.
- Lead routing gaps: no WhatsApp notice to farmer on assignment / to dealer on re-route; dealer win/loss doesn't close the farmer's interest (dealer context can't write farmer rows: needs a system hook); declined consent not recorded from the app; phone-reputation anti-abuse not done.
- Consent texts (en/hi/mr) need legal + native-speaker review before pilot.
- Community gaps: voice posts + STT adapter, real LLM classifier (pick provider; benchmark Marathi/Hindi), admin moderation UI (API only), warn/suspend/appeal, Redis feed cache, deploy-time abuse blocklist per language (native speakers).
- Rentals gaps: WhatsApp push to nearby owners on a new need (cap 1/owner/day), WA relay instead of in-app contact, rental-host verification, voice needs, legal disclaimer copy, admin UI for disputes.
- Run `make up` locally with Docker Desktop to finish E0 "done when".
- Put `AGRODESK_PROJECT.md` at repo root (copy from the Claude Project).
- Marathi / Hindi translations are machine-authored; book a native-speaker pass on src/messages/{mr,hi}.json before pilot.
- Run `npm run e2e:install && E2E_OWNER_FIXED_CODE=... npm run e2e` locally once a dev user is seeded, to verify the Playwright smoke test.
- Marathi + Hindi opt-out phrases are first-pass; book a native-speaker review before pilot (`packages/channels/whatsapp/../message_service.py OPT_OUT_DEVANAGARI`).
- Pick a BSP: Gupshup / Interakt / WATI / WhatsApp Cloud API. Start the business-account application on day 1 (open decision L.3-1).
- Pick an embedding provider (OpenAI / Voyage / Cohere / self-hosted) and benchmark Marathi + Hindi retrieval before Mitra goes live.
- At > ~10k chunks for a single dealer, migrate kb_chunks.embedding from JSONB to pgvector `vector(384)` and switch kb_service.search to SQL cosine (`<=>`).
- Start E8 (Mitra lead agent on WhatsApp): plan first.
- On your Windows machine: install Python 3.12+, `make up`, `cd apps/api && pip install -e ".[dev]" && alembic upgrade head && pytest`, then `python -m scripts.bootstrap_admin "+91<your-phone>" "Prasad"` to create the first platform admin.

## Human tasks (start day 1, in parallel)
- [ ] Apply for WhatsApp BSP account and submit templates
- [ ] Start baseline measurement (docs/baseline-sheet.md)
- [ ] Book farmer and dealer interviews (docs/interview-guides.md)
- [ ] Start collecting consented call recordings / voice notes for evals

## Blockers
- Decision needed: fate of the existing agrodesk.xyz voice agent (retire / reuse for E13 / keep separate).
- Timeline target not set (brief says 16 weeks; team wants faster).
