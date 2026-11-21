# Agrodesk v1.0 MVP — System Design

**Scope:** v0.1 foundation + v1.0 MVP only. v1.5+ features are noted as "design forward for, build later."
**Audience:** the four-person build team + any outside reviewer.
**Companion to:** `AGRODESK_PROJECT.md` (product brief). Where the brief and this doc disagree, flag it and update one — don't quietly diverge.

---

## 1. Requirements

### 1.1 Functional (MVP)
- Dealer staff can add a lead in under 15s, see Today's Tasks, log outcomes with one tap.
- Every new lead gets an automated WhatsApp reply inside 5 minutes during business hours, and a scheduled follow-up.
- A WhatsApp agent (Mitra) qualifies and scores leads, hands off to a human on price/discount/delivery/complaint/low-confidence.
- Owner gets a daily WhatsApp brief and a single-screen dashboard.
- A separate WhatsApp line (Shivar) answers farmer questions and creates a lead only with explicit consent.
- Admin team can onboard a dealer, load their knowledge base, and see usage.
- Dealer is billed monthly via Razorpay with GST invoices; usage credits with soft+hard caps.

### 1.2 Non-functional
| Dimension | Target |
|---|---|
| **Scale (MVP)** | 1 pilot dealer, then 5-20. 30-40 leads/dealer/month ≈ 2-25 leads/day across tenants. |
| **Scale (design for)** | 200 dealers, ~100 msg/dealer/day, ~2k msg/min peak during campaign bursts. |
| **Latency** | p95 API ≤ 300ms. First automated WhatsApp reply ≤ 5 min (not real-time; async is fine). Webhook ack ≤ 2s. |
| **Availability** | 99.5% business hours (8am-9pm IST). Overnight degradation acceptable. |
| **Durability** | Zero message loss (outbox). Daily backups + PITR. |
| **Consistency** | Strong for leads/tasks/payments. Eventual for agent summaries and analytics. |
| **Cost ceiling** | AI + WhatsApp + infra < 40% of per-dealer subscription at the 90th percentile dealer. |

### 1.3 Constraints
- Team of 4, one is the founder/product owner (not full-time coder).
- Timeline: pressure to ship MVP in ~4-6 weeks of build + 4 weeks pilot.
- Stack locked in brief Part F.1 (Python/FastAPI, Next.js, Postgres+pgvector, Redis+Celery, LangGraph).
- India-only, English/Marathi/Hindi. Mumbai region, DPDP Act, TRAI rules on outbound.
- WhatsApp routed through a BSP (Gupshup / Interakt / WATI — not decided).
- No customer payments through our rails. Razorpay is for our own subscription billing only.

---

## 2. High-Level Design

### 2.1 Component map

```
┌────────────────┐        ┌──────────────────┐        ┌───────────────────┐
│ Dealer PWA     │◄──────►│   FastAPI (api)  │◄──────►│   Postgres 16     │
│ Next.js        │  REST  │                  │        │   + pgvector      │
└────────────────┘        │  - auth/tenant   │        │   + RLS           │
                          │  - CRUD services │        └───────────────────┘
┌────────────────┐        │  - admin         │        ┌───────────────────┐
│ Farmer / WA    │        │                  │        │   Redis           │
│ (via BSP)      │─webhook┤                  │────────┤   broker + cache  │
└────────────────┘        └─────┬────────────┘        └─────────┬─────────┘
                                │                               │
                                ▼                               ▼
                          ┌──────────────┐              ┌───────────────┐
                          │ Outbox       │              │ Celery        │
                          │ (table in PG)│              │ workers + beat│
                          └──────┬───────┘              └──┬──────┬─────┘
                                 │                         │      │
                     ┌───────────▼───────────┐      ┌──────▼──┐ ┌─▼────────┐
                     │ Sender worker         │      │ Agent   │ │ Planner  │
                     │ (WhatsApp/SMS/Push)   │      │ worker  │ │ (beat)   │
                     └───────────┬───────────┘      │ LangGraph│└──────────┘
                                 │                  └──┬──────┘
                          BSP ◄──┘                     │
                                           LLM/Embed ◄─┘   Langfuse ◄─ traces
```

### 2.2 Data flow — inbound lead from a Facebook ad (the critical path)

```
1. Facebook lead form submission
2. BSP webhook → /webhooks/whatsapp or /webhooks/leadgen
3. api verifies signature → creates customer (if new) + lead
   → writes lead_event + outbox(send_first_message) + task(human_followup_t+5min)
   → all in one DB transaction
4. Sender worker picks up outbox row → sends WhatsApp template via BSP
   → updates message status + outbox.status
5. Farmer replies → BSP webhook → stored in messages, conversation thread
6. Agent worker picks up the new message → runs Mitra graph:
   load_context → guard_input → classify → qualify → guard_output → outbox
7. Planner beat task (nightly + on-outcome) → generates tasks[] for next day
8. Staff logs outcome in PWA → lead_event + new next_action_at
```

### 2.3 API contract style
- **REST + JSON**, single internal API. OpenAPI generated from Pydantic. No GraphQL, no gRPC for MVP.
- Versioned under `/v1`. Breaking changes bump the prefix.
- All tenant endpoints scoped by the auth session; `dealer_id` is **never** a path or body parameter sent by a client.
- Standard error shape: `{"error": {"code": "...", "message": "...", "details": {}}}`.
- Idempotency via `Idempotency-Key` header on all `POST` that send or charge.

### 2.4 Storage choices
| Data | Store | Why |
|---|---|---|
| Transactional (leads, tasks, messages) | Postgres | ACID, RLS, familiar. |
| Embeddings | pgvector in the same Postgres | One store, tenant filter trivial. Revisit at ~10M chunks. |
| Agent state (LangGraph checkpoints) | Postgres (checkpointer) | Same transaction boundary as business data. |
| Message bodies + media | Postgres for text + object storage (S3-compatible) for media | Postgres is fine for text at MVP volume; blobs don't belong in a row. |
| Cache + queue | Redis | Celery broker, short-lived rate-limit counters, no cache-as-truth. |
| Call recordings (E13 stretch) | Object storage, server-side encrypted | Retention policy applied via lifecycle rules. |

---

## 3. Deep Dive

### 3.1 Multi-tenancy — defense in depth
1. Auth session holds `user_id` + `dealer_id`.
2. Every request handler calls `set_current_dealer(session)` before any DB query, which runs `SET LOCAL app.current_dealer = '<uuid>'`.
3. **RLS policy on every tenant table:** `USING (dealer_id = current_setting('app.current_dealer')::uuid)`.
4. Service functions **also** filter by `dealer_id` from session (belt-and-braces).
5. Cross-tenant test is required for every new endpoint. CI fails if the test isn't present (grep-based lint rule).
6. Agent tools receive `dealer_id` from graph state, never from LLM output.

**Trade-off:** shared schema + RLS is simpler than schema-per-tenant or DB-per-tenant and scales fine to ~200 dealers. Revisit when a large group wants a dedicated DB for compliance or noise isolation.

### 3.2 Data model (MVP tables only — full list in brief Part G)

Core shape (every tenant row carries `id uuid`, `dealer_id uuid`, `created_at`, `updated_at`):

```
dealers, users
customers (phone unique per dealer, consent flags, language)
leads (stage, score, next_action_at, source, campaign)
lead_events (append-only audit)
tasks (user, due_at, outcome)
conversations, messages (idempotency_key unique)
outbox (kind, payload, status, attempts, next_attempt_at)
kb_documents, kb_chunks (pgvector, dealer_id nullable for shared catalogue)
consents (text_shown, granted, recorded_at)
agent_runs (trace, prompt_version, cost, tokens)
ad_spend, plans, subscriptions, usage_ledger, feature_flags, audit_log
```

**Indexing for the hot paths:**
- `leads (dealer_id, next_action_at)` — Today's Tasks query
- `leads (dealer_id, stage)` — funnel
- `leads (dealer_id, owner_user_id, next_action_at)` — per-staff task list
- `customers (dealer_id, phone)` — duplicate detection (unique constraint)
- `messages (conversation_id, created_at)` — thread load
- `outbox (status, next_attempt_at)` — sender poll
- vector index on `kb_chunks` with partial filter per `dealer_id` where it matters

**State machine for `leads.stage`:** `new → contacted → qualified → visit_planned → negotiation → (won | lost)`. Transitions enforced in a service function; every change writes `lead_events`. Open leads **require** `next_action_at`; `lost` requires `lost_reason`. These are DB constraints + service checks.

### 3.3 WhatsApp gateway — the hard part

**Why it's hard:** two-way messaging with a 24-hour session window, templates needing pre-approval, provider rate limits, webhook-at-least-once delivery, opt-out as a hard rule.

**Design:**

```
                                     ┌──────────────┐
    POST /webhooks/whatsapp ────────►│ verify sig   │
                                     │ idempotency  │─no─► 200 OK (dedupe)
                                     └──────┬───────┘
                                            │ yes
                                            ▼
                                    one DB transaction:
                                    - insert message
                                    - update conversation
                                    - enqueue agent_run task (Redis)
                                            │
                                            ▼
                                        200 OK
                                            │
                                            ▼
                            (async) agent worker runs Mitra graph,
                            writes outbox row for the reply
                                            │
                                            ▼
                     sender worker loop (every 1-2s):
                     pick outbox rows status='pending', attempts<N, next_attempt_at<now
                     send via BSP adapter → on success mark 'sent'
                     on failure: attempts++, exponential backoff, dead-letter at N=6
```

**Rules baked into the adapter interface:**
- `send(message, within_window: bool)` — if `within_window=False`, must use an approved template; the adapter rejects a raw body.
- `send(..., opt_out_check=True)` — adapter calls the consent service; reject if opted out.
- `verify_signature(headers, body)` — called before the DB transaction.
- Webhook idempotency: `provider_message_id` is unique in `messages`; a duplicate webhook does nothing.

**Trade-off:** polling the outbox from Celery is simpler than a dedicated event bus and plenty fast at MVP scale. At stage-3 scale (200+ dealers), move to per-dealer partitioned queues or Postgres `LISTEN/NOTIFY`.

### 3.4 Agent runtime (Mitra, Shivar)

- **LangGraph graph per agent**, Postgres checkpointer, one thread per `(customer_id, channel)`.
- Graph nodes are **Python functions**; the LLM is called from inside specific nodes (`draft_answer`, `extract_fields`), not between them. Scheduling and state are deterministic.
- **Structured output** via function-calling / JSON schema. Validated with Pydantic; invalid → retry once, then hand off to human.
- **Guards are code, not prompt text:**
  - `guard_input`: opt-out check, abuse classifier, prompt-injection patterns.
  - `guard_output`: regex + semantic checks for price promises, delivery date, subsidy eligibility, non-approved discounts. Blocked outputs create a human task instead.
- **Tool allow-list:** Mitra has `retrieve_kb`, `score_lead`, `create_task`, `update_lead`, `send_message_intent`. Nothing else. Tools read `dealer_id` from graph state.
- **Model router:** cheap model (e.g. small/fast) for routine replies; stronger model when `guard_input` flags complexity or when `retrieve_kb` returns low-confidence hits. Router choice is a single config file.
- **Rolling summary:** after N messages, replace history with a 200-token summary + last 4 turns. Keeps cost flat per conversation.

**Observability:** every agent run writes `agent_runs` (prompt version, model, tokens, cost, latency, outcome) and a Langfuse trace with a link from the lead detail page ("Why this reply?").

### 3.5 Scheduling — the Planner

Mostly code, not AI. Celery beat jobs:
| Job | Cadence | Does |
|---|---|---|
| `generate_tasks` | 00:30 IST nightly | For every open lead with `next_action_at <= today`, upsert a task for the assigned staff. |
| `send_daily_brief` | 08:30 IST (per-dealer configurable) | Build Munshi brief, send via outbox. |
| `overdue_alerts` | hourly, business hours | Find leads overdue > N hours; push to owner. |
| `silent_lead_sequence` | hourly | Enforce the "max 3 automated messages in 5 days" rule, then stop + create a human task. |
| `usage_rollup` | hourly | Aggregate `usage_ledger` for billing. |
| `stale_lead_check` | daily | Flag leads with no activity > 14 days. |

Idempotency on every job: `(job_name, logical_date, lead_id)` is a unique key in a `job_runs` table to prevent double-firing on retry.

### 3.6 Caching strategy

**Policy: cache nothing by default.** Add caching only when a specific query shows up as hot.

Expected caches at MVP:
| Target | TTL | Why |
|---|---|---|
| Dealer config (`business_hours`, `brands`, `templates`) | 60s in-process + Redis | Read on every inbound message. |
| Feature flags | 30s | Hot per-request. |
| KB retrieval (cold cases) | none | Queries are user-driven and varied; cache would thrash. |
| Owner dashboard aggregates | 5 min | Fine for a dashboard; rebuilt by a cron. |

No read-through cache on primary tables. Cache invalidation is done by writing a tombstone to Redis on the update path for the two caches that exist.

### 3.7 Error handling and retries

| Class | Strategy |
|---|---|
| **Transient external** (BSP 5xx, LLM timeout) | Exponential backoff with jitter, max 6 attempts, dead-letter to `outbox.status='failed'` + owner alert. |
| **Permanent external** (BSP 4xx, invalid number) | Mark `messages.status='rejected'`, surface in lead timeline, no retry. |
| **DB deadlock** | Automatic retry twice in the transaction wrapper, then 500 with error id. |
| **Validation** | Return 422 with field-level details. Never log request body (may contain PII). |
| **Agent failure** (model error, guard trip, unparseable JSON) | **Never silent.** Create a human task with the last message and a reason, mark the lead `needs_human=true`. |
| **Idempotency replay** | `Idempotency-Key` stored for 24h; same key + same body → previous response; same key + different body → 409. |

### 3.8 Front-end
- Next.js App Router, strict TS, PWA with a service worker for offline-tolerant writes (Quick Add, outcomes).
- Writes queued in IndexedDB when offline; replayed on reconnect with the server's `Idempotency-Key` to avoid duplicates.
- Push via FCM on Android; iOS PWA push is unreliable, so fallback is WhatsApp/SMS for overdue alerts.
- i18n with `next-intl`; message catalogs committed in-repo (English, Marathi, Hindi).

---

## 4. Scale and Reliability

### 4.1 Load estimates (sanity check)

**Pilot (1 dealer):** ~1-2 leads/day, ~20-50 WA messages/day, ~5 agent runs/day. **Everything fits on one $50/mo VM** if we're not careful.

**Design-for (200 dealers):**
- Leads: 200 × 2/day = 400/day = ~0.3/min average.
- WA messages: 200 × 100/day = 20,000/day = ~14/min average, ~2k/min during a campaign burst.
- Agent runs: 200 × 50/day = 10,000/day = ~7/min average.
- LLM tokens: ~400 tokens/exchange × 10k = 4M tokens/day. At ~$0.5-$2 per 1M input tokens (cheap model), ~$2-$10/day across tenants, before stronger-model routing.
- DB: ~10k-50k inserts/day across `messages`, `lead_events`, `agent_runs`. Comfortably one Postgres instance.

**None of this is hard-scale.** The MVP's scale problem is correctness under bursts (a dealer's ad campaign spiking 10x for a day), not raw QPS.

### 4.2 Horizontal scaling plan
- **API (FastAPI/uvicorn):** stateless, behind a load balancer, N replicas. Scale by replica count.
- **Celery workers:** two pools — `agents` (slow, LLM-bound, low concurrency) and `senders` (fast, I/O-bound, higher concurrency). Independent scaling.
- **Celery beat:** single leader (standard Celery constraint). Acceptable at MVP; use `celery-redbeat` for HA if it ever becomes a problem.
- **Postgres:** single primary at MVP. Read replica added when the dashboard starts hurting the primary (expected at ~50 dealers).
- **Redis:** single-node managed; cluster not needed at MVP volume.

### 4.3 Failover and redundancy
- Managed Postgres with PITR + daily backups + quarterly restore drill (runbook in `docs/runbooks/`).
- BSP adapter interface means we can migrate providers in days, not months. Document a "BSP failover plan" even if we never use it.
- LLM provider: router config supports fallback to a secondary vendor on 5xx or timeout > 10s.
- Circuit breakers on BSP, LLM, SMS — if error rate > 20% over 5 min, suspend non-essential sends (keep inbound), alert the owner.
- **Kill switches:** per-dealer and global feature flags for `agent_enabled`, `whatsapp_enabled`, `voice_enabled`. One toggle disables automated sending.

### 4.4 Monitoring and alerting

| Signal | Source | Alert threshold |
|---|---|---|
| API p95 latency | app metrics | > 500ms for 5 min |
| Webhook ack p95 | app metrics | > 2s for 5 min |
| Outbox queue depth | PG query | > 100 for 10 min (sender behind) |
| Outbox failure rate | PG query | > 5% in 15 min |
| Agent guard-trip rate | `agent_runs` | > 10% in 1 hour (probable prompt regression) |
| LLM cost per dealer | `usage_ledger` | > 80% of monthly credit → soft; 100% → hard stop + owner alert |
| 1st-response SLO | `lead_events` | > 5 min in business hours → page |
| DB connections | PG | > 80% of pool |

**Tooling:** Sentry for errors, Langfuse for agent traces, Prometheus + Grafana (or managed equivalent) for the rest. Structured JSON logs with `dealer_id` + `trace_id`.

---

## 5. Trade-offs — decisions made, with the loser noted

| # | Decision | Alternative | Why we chose it | When to revisit |
|---|---|---|---|---|
| 1 | Monolith FastAPI + Celery | Microservices from day 1 | Team of 4, one bounded context, deploy speed matters more than service boundaries. | > 10 engineers or a team wants independent deploy cadence. |
| 2 | Shared DB, RLS | Schema-per-tenant / DB-per-tenant | Simpler ops, cheaper, RLS is a real security boundary when combined with service-layer checks. | A dealer group with compliance needs a dedicated DB, or ~200+ dealers cause noisy-neighbour issues. |
| 3 | Postgres + pgvector for embeddings | Dedicated vector DB (Pinecone/Qdrant) | One store, one backup, dealer filter trivial, no network hop. | > 10M chunks or latency on vector search degrades. |
| 4 | REST + JSON | GraphQL, tRPC, gRPC | Boring, well-known, OpenAPI → generated TS client. GraphQL's overfetch win doesn't matter for a focused mobile PWA. | Public API opens up with varied consumers. |
| 5 | Outbox table in Postgres + Celery poller | Kafka, SQS, NATS | Same transaction as business data (zero loss), no extra infra, poll interval of 1-2s meets the 5-minute SLO 50x over. | > 200 dealers or > 100k outbox rows/day. |
| 6 | LangGraph for agent orchestration | Custom state machine, LlamaIndex agents, bare chains | Explicit state + checkpointer makes resume and audit possible. Low lock-in because our graph nodes are plain Python. | A cheaper/simpler alternative with checkpointing emerges. |
| 7 | BSP adapter interface | Direct WhatsApp Cloud API | Faster onboarding, template approval help, India-friendly billing. Interface keeps the escape hatch. | WhatsApp Cloud API becomes materially cheaper + onboarding gets easier. |
| 8 | Hosted LLMs behind a router | Self-hosted small models | Marathi/Hindi quality at MVP is not a bet we can win self-hosted. Router lets us mix. | Marathi/Hindi open-weights reach parity + our volume justifies the ops cost. |
| 9 | PWA (Next.js) | Native Android app | 80% of the value, 20% of the effort. Push is the only real loss; we cover with WhatsApp fallback. | Push becomes essential or we need native call integration. |
| 10 | Voice pilot runs **outside** LangGraph (Pipecat/LiveKit) | Shoehorn voice into LangGraph | Live audio needs sub-second turns; LangGraph is turn-based + async. Keep responsibilities clean. | LangGraph adds real-time primitives. |
| 11 | No customer payments through Agrodesk | Collect dues through our rails | Legal and tax surface area explodes. Dealer→customer stays direct. | Only if there's a very strong business case **and** a payments partner. |
| 12 | Single region (Mumbai) | Multi-region active-active | India-only product, cost and complexity don't earn their keep. | Expansion outside India. |

---

## 6. What we'd revisit as the system grows

| Stage | Trigger | Change |
|---|---|---|
| ~20 dealers | Dashboard slows the primary | Add a read replica; point dashboard + analytics queries there. |
| ~50 dealers | Message table > 5M rows | Partition `messages`, `lead_events`, `agent_runs` by month. |
| ~100 dealers | WhatsApp burst > 500 msg/min per BSP limit | Multiple BSP numbers per dealer group; per-dealer rate limiters in the sender worker. |
| ~200 dealers | Outbox poll lag spikes | Per-dealer sender queues or move to Postgres `LISTEN/NOTIFY`. |
| LLM cost > budget | Monthly cost ledger shows it | Aggressive prompt caching, smaller default model, longer rolling summaries, offline fine-tune for routine replies. |
| Agent errors become subtle | Human review finds silent misclassifications | LLM-as-judge in evals + weekly human spot-check on a sample. |
| Voice at scale (E13 → v2.5) | Pilot results clear legal review | Dedicated voice runtime fleet, per-region telephony providers, STT/TTS fallback vendors. |
| A dealer group wants isolation | Compliance ask or a serious noisy-neighbour event | Move that tenant to a dedicated DB using the existing RLS boundary as the seam. |

---

## 7. Assumptions (flag if any of these turn out wrong)

1. BSP approval + first template approval takes 1-3 weeks — we apply on day 1 of E0.
2. A single Mumbai-region Postgres (managed) is enough through ~100 dealers.
3. Facebook Lead Ads → BSP webhook → us is the dominant lead source. Non-FB sources arrive via Quick Add or CSV import.
4. Marathi/Hindi quality on hosted LLMs is "good enough" with grounding + rolling summaries. **To be measured on the eval set before pilot.**
5. Dealers will accept their own WA business number used by Mitra. **To be validated with the pilot dealer.**
6. Pilot dealer staff will log outcomes every day if the UI is one-tap. **The baseline measurement + 2-week parallel run will prove this.**
7. The "never promise price/delivery/subsidy" guardrail is enforceable by code + small eval set at MVP volume; LLM-judge not required yet.

---

## 8. What this doc deliberately does **not** cover

- v1.5+ features (service, used stock, dues, marketplace, subsidies, Biocred) — brief Part D has the roadmap, revisit before each version.
- Pricing model math — needs the cost-per-lead sheet from Epic E14.
- Hiring plan — product/people doc, not system design.
- Full compliance analysis — needs a lawyer; brief Part J.8 is a starting checklist, not a verdict.

---

_Change log: 2026-11-21 — first version, Prasad + Claude Opus 4.7. Update alongside DECISIONS.md whenever a numbered trade-off in §5 changes._
