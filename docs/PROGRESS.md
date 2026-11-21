# PROGRESS

## Status (2026-11-21)
- Epic E0 scaffold created: monorepo layout, docker-compose (Postgres 16 + pgvector, Redis), Makefile, CI, API health endpoint + test.
- Verified (Python 3.13, cloud workspace): ruff lint + format clean, pytest 1 passed.
- Not verified: `make up` (Docker not available in the Cowork VM; run on your Windows machine with Docker Desktop).

## Next
- Run `make up` locally with Docker Desktop to finish E0 "done when".
- Put `AGRODESK_PROJECT.md` at repo root (copy from the Claude Project).
- Start E1 (auth and tenancy): plan first, wait for approval.

## Human tasks (start day 1, in parallel)
- [ ] Apply for WhatsApp BSP account and submit templates
- [ ] Start baseline measurement (docs/baseline-sheet.md)
- [ ] Book farmer and dealer interviews (docs/interview-guides.md)
- [ ] Start collecting consented call recordings / voice notes for evals

## Blockers
- Decision needed: fate of the existing agrodesk.xyz voice agent (retire / reuse for E13 / keep separate).
- Timeline target not set (brief says 16 weeks; team wants faster).
