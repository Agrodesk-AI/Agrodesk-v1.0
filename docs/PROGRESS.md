# PROGRESS

## Status (2026-11-21)
- Epic E0 scaffold created: monorepo layout, docker-compose (Postgres 16 + pgvector, Redis), Makefile, CI, API health endpoint + test.
- Verified (Python 3.13, cloud workspace): ruff lint + format clean, pytest 1 passed.
- Not verified: `make up` (Docker not available in the Cowork VM; run on your Windows machine with Docker Desktop).

## Done
- E3.1 shipped: offline write queue (IndexedDB) + next-intl en/mr/hi catalogs + Playwright smoke test scaffold. Build passes, typecheck clean, 7 routes.
- E3 shipped: Next.js 15 PWA shell + auth + Today's Tasks + Leads list + Quick Add + Lead detail with timeline + transitions.
- E2 shipped: customers + leads core API with state machine + event log (27/27 tests pass).
- E1 shipped: auth, tenancy with RLS, cross-tenant test green.
- docs/SYSTEM_DESIGN.md written — MVP architecture, data flow, trade-offs, scale plan, assumptions.

## Next
- Run `make up` locally with Docker Desktop to finish E0 "done when".
- Put `AGRODESK_PROJECT.md` at repo root (copy from the Claude Project).
- Marathi / Hindi translations are machine-authored; book a native-speaker pass on src/messages/{mr,hi}.json before pilot.
- Run `npm run e2e:install && E2E_OWNER_FIXED_CODE=... npm run e2e` locally once a dev user is seeded, to verify the Playwright smoke test.
- Start E4 (CSV/XLSX bulk import) or E5 (Today's Tasks planner + nightly beat): plan first.
- On your Windows machine: install Python 3.12+, `make up`, `cd apps/api && pip install -e ".[dev]" && alembic upgrade head && pytest`, then `python -m scripts.bootstrap_admin "+91<your-phone>" "Prasad"` to create the first platform admin.

## Human tasks (start day 1, in parallel)
- [ ] Apply for WhatsApp BSP account and submit templates
- [ ] Start baseline measurement (docs/baseline-sheet.md)
- [ ] Book farmer and dealer interviews (docs/interview-guides.md)
- [ ] Start collecting consented call recordings / voice notes for evals

## Blockers
- Decision needed: fate of the existing agrodesk.xyz voice agent (retire / reuse for E13 / keep separate).
- Timeline target not set (brief says 16 weeks; team wants faster).
