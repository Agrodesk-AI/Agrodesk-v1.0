# Agrodesk — System Design v2 (two-sided app)

**Supersedes** `docs/SYSTEM_DESIGN.md` on the new scope (dealer/farmer split, community, rental exchange, subsidies, trust). Everything from v1 that is not re-decided here still stands.
**Source of truth for features:** `docs/AGRODESK_FINAL_APP_FEATURES.md`.
**Date:** 2026-11-22. Author: Prasad + Claude Opus 4.7.

---

## 1. Requirements

### 1.1 Functional — what the system now does
- One account per phone, **multiple profiles**: dealer (owner / staff), farmer, expert. A single phone can be a dealer and a farmer.
- **Dealer mode** (brief Part 4): the v1 CRM + planner + Mitra + KB + billing + used-inventory + service + recovery.
- **Farmer mode** (brief Part 5): WhatsApp-first Guide (Shivar), Yojana subsidies, rental exchange, community feed, used-tractor browsing, price board, trust signals, expert Q&A.
- **Cross-user flows**: consented farmer→dealer lead routing, dealer listings in farmer feeds, farmer rental needs matched to nearby owners, subsidy interest becoming a warmer lead.
- **Moderation** across all user-generated content (posts, replies, listings, voice notes).
- **Verification** for dealers (GST or authorisation doc), experts (credentials), farmers for high-trust actions (private seller, rental host).

### 1.2 Non-functional
| Dimension | Target |
|---|---|
| **Scale — pilot** | 1 tehsil near Nashik, 3-5 dealers, 30-50 farmers, 1 expert partner. |
| **Scale — design-for** | 1 state (Maharashtra), ~5000 tehsils' worth of data, 200 dealers, 50-200k farmers. |
| **Latency** | p95 API ≤ 300 ms; webhook ack ≤ 2 s; first automated WhatsApp reply ≤ 5 min; voice STT turnaround ≤ 10 s; community feed load ≤ 1.5 s on 4G. |
| **Availability** | 99.5% business hours; farmer-side lower overnight is acceptable; dealer kill switch always available. |
| **Durability** | Zero message loss (outbox). Daily PITR backups. Voice media retained per policy (default 180 days). |
| **Moderation SLO** | Flagged content reviewed within 24 h. |

### 1.3 Constraints
- Team of 4, pilot-first.
- Pilot geography is **one tehsil**; expand tehsil-by-tehsil.
- Stack carried forward from v1: FastAPI, Next.js PWA, Postgres + pgvector + RLS, Redis + Celery, LangGraph agents, WhatsApp BSP adapter, hosted LLMs + embedding adapters.
- Legal still open on DPDP (incl. age), rentals disclaimers, intermediary duties, recording consent.
- India-only, Marathi + Hindi + English first.

---

## 2. High-level design

### 2.1 Component map (changes from v1 in **bold**)

```
┌────────────────┐        ┌──────────────────────┐        ┌───────────────────┐
│ Dealer PWA     │        │   FastAPI (api)      │        │   Postgres 16     │
│ (Next.js)      │────────│  v1 CRM + planner +  │────────│   + pgvector      │
│                │        │  billing + KB        │        │   + RLS           │
├────────────────┤        │                      │        │                   │
│ Farmer PWA     │────────│  **Farmer services:**│        │   geo/location    │
│ (community,    │        │   community feed,    │        │   data + tehsil   │
│ rent, browse)  │        │   rental matcher,    │        │   neighbours      │
├────────────────┤        │   subsidy rules,     │        └───────────────────┘
│ Farmer WA      │─webhook│   expert Q&A,        │        ┌───────────────────┐
│ (via BSP)      │─▶      │   moderation queue   │        │   Object storage  │
└────────────────┘        │                      │────────│   (voice, photos, │
                          │  **Admin console:**  │        │   docs, exports)  │
┌────────────────┐        │   dealer verif,      │        └───────────────────┘
│ Expert PWA     │────────│   scheme library,    │
│ (Q&A queue)    │        │   expert verif,      │        ┌───────────────────┐
└────────────────┘        │   moderation         │        │   Redis           │
                          └──┬────────────────┬──┘        │   broker + cache  │
                             │                │           └──┬──────┬─────────┘
                    outbox   │                │ events       │      │
                             ▼                ▼              ▼      ▼
                       ┌────────────┐   ┌──────────────┐  ┌────────────────┐
                       │ Sender     │   │ Agent runner │  │ Celery workers │
                       │ (WA, SMS,  │   │ (LangGraph)  │  │ + beat         │
                       │  push)     │   │              │  │ (planner,      │
                       └─────┬──────┘   └──┬───────────┘  │  outbox,       │
                             │             │              │  moderation,   │
                       BSP ◀─┘      LLM/   │              │  stt,          │
                                    Embed◀─┘              │  rental match, │
                                                          │  digests,      │
                                                          │  scheme-review)│
                                                          └────────────────┘
                                                               │
                                                        ┌──────▼─────┐   ┌──────┐
                                                        │ STT/TTS    │   │Maps/ │
                                                        │ provider   │   │Geo   │
                                                        └────────────┘   └──────┘
```

### 2.2 The critical path, end-to-end
Still the same promise as v1: **no lead and no farmer question dies on the vine.** Three path classes:

**A. Dealer-only path** (v1 unchanged): Facebook lead → BSP webhook → dealer tenant → Mitra outbox → first reply ≤ 5 min → Planner builds tasks → owner sees dashboard + brief.

**B. Farmer-initiated path** (new):
```
1.  Farmer opens WhatsApp or PWA → signup/login, chooses language.
2.  Shivar (farmer front agent) answers from the shared KB + farmer memory.
3.  Buying intent detected → explicit consent prompt (plain language, one tap).
4.  Router picks dealer(s): brand match + same tehsil → neighbours → district.
    Verified Agrodesk dealer only. 1-3 dealers per lead.
5.  Lead lands on dealer board with source="Agrodesk Guide" + consent evidence.
6.  Dealer SLA timer (configurable per tier, default 4h business hours).
7.  If no response → re-route to the next dealer. Previous dealer sees "re-routed".
8.  Mitra first reply still ≤ 5 min from the moment the lead reaches the dealer.
```

**C. Community path** (new):
```
Farmer posts an Ask or a Need → moderator agent pre-screens → if clean,
 → publishes to tehsil's "Near me" feed (village-first ranking)
 → nearby users with matching interest/equipment get a capped WA alert
 → replies threaded, voice supported (STT + editable transcript)
 → unanswered Asks (24h) → escalate to a verified expert's queue
 → expert drafts (AI-assisted) → approves/corrects → pinned as the accepted answer
 → trust signals updated (helpful answers, response rate)
```

### 2.3 API contract style
Same as v1: REST + JSON under `/v1`, OpenAPI generated from Pydantic, idempotency keys on all state-changing POSTs, consistent error shape. New surfaces:

- `/v1/farmer/*` for the farmer-mode endpoints
- `/v1/community/*` for the feed and replies
- `/v1/rentals/*` for the equipment exchange
- `/v1/subsidies/*` for scheme discovery + eligibility
- `/v1/experts/*` for the expert queue
- `/v1/admin/moderation/*` and `/v1/admin/schemes/*` for the back-office

### 2.4 Storage choices
| Data | Store | Why |
|---|---|---|
| All transactional | Postgres (one logical DB, RLS) | Carried from v1 |
| Vectors (KB + community search) | pgvector, same DB | v1 decision stands |
| **Voice notes, photos, bill images, scheme PDFs** | S3-compatible object storage, private, signed-URL reads | Large binaries don't belong in rows |
| **Audio transcripts** | Postgres `messages`/`posts` row as text (+ pointer to audio) | Transcripts are first-class content and searched |
| **Location catalog** (states/districts/tehsils/villages + neighbours) | Postgres, shared (no `dealer_id`); read-open, write-admin-only | Looked up constantly; small enough to index-sit in RAM |
| Cache + queue | Redis | Celery broker, short-lived rate-limit counters, feed page cache |
| Agent traces | Langfuse | v1 decision stands |

---

## 3. Deep dive — what's architecturally new

### 3.1 Identity: accounts, profiles, multiple roles

```
accounts(id, phone UNIQUE, created_at, locked, age_verified_at, dob)
    ↓ 1:N
profiles(id, account_id, kind, display_name, language, status)
   kind ∈ {dealer_owner, dealer_staff, farmer, expert, platform_admin}
    ↓ joined per-kind to dealer_staff / farmers / expert_profiles
```

- Phone OTP creates or loads `accounts`.
- Each profile is a separate row with its own permissions and its own WhatsApp consent scope.
- **Profile switcher** in the PWA; WhatsApp routes to the latest active profile for that phone unless the message content is clearly in-scope for another one (e.g. a message to a dealer's business number resolves the dealer_staff profile for that phone, if any, else the farmer profile).
- **RLS** uses the active profile's dealer_id (dealer side) or user_id (farmer side). The session dependency sets `app.current_dealer` or `app.current_farmer` + `app.profile_kind`.
- **Data isolation across profiles**: a dealer staff's inbox never shows up in their farmer-side feed. Enforced by the same RLS pattern as v1 — one more GUC (`app.current_farmer`) and matching policies on farmer-scoped tables.

**Age gate:** DOB stored in `accounts`, OTP required. Self-declaration is weak — legal advice gate on verifiable age checks before public launch (brief 2.4, 11).

### 3.2 Location model — hierarchy + neighbours

```
states(id, code, name_en, name_mr, name_hi)
districts(id, state_id, code, name_en, name_mr, name_hi)
tehsils(id, district_id, code, name_en, name_mr, name_hi)
villages(id, tehsil_id, code, name_en, name_mr, name_hi, slug_search)
tehsil_neighbours(tehsil_id, neighbour_tehsil_id, order)  -- symmetric, from LGD/admin source
dealer_service_areas(dealer_id, tehsil_id, is_home)
```

- Seeded from an **official source** (Local Government Directory). Imported as a one-off alembic data migration + a periodic re-sync job (schemes and village names change).
- **"Nearby" is not raw distance.** It's the `tehsil_neighbours` map plus an `order` for routing priority. This is the single joint that lead routing, rental matching, and community feed ranking all sit on — one fix, three systems.
- Farmer position is **village-level only**. Exact coordinates are never stored unless the farmer explicitly shares one for a specific purpose (e.g. "add my farm pin to my offer listing"), and even then it's in a separate `location_shares` table with a purpose + retention.

**Why this matters architecturally:** every farmer-side query that needs "near me" pulls from a cached view keyed by `tehsil_id`, not from a live distance computation. That keeps page loads fast without PostGIS (which we can still add if truly distance-based search ever becomes a feature).

### 3.3 Consented lead routing (Guide / marketplace → dealer)

**Routing service** (sync):
```
1. Identify intent: Shivar's `classify_intent` returns {buying_intent=true, brand_hint, hp_range, timeline}.
2. Consent: prompt the farmer with the exact text we will store, record YES/NO in `consents`.
3. Find candidates:
   candidates = dealers
                where verified = true
                  and brand_hint in dealers.brands
                  and (home_tehsil = farmer.tehsil
                       or tehsil in dealer_service_areas
                       or tehsil in tehsil_neighbours(farmer.tehsil))
                order by (home match, nearest order, response-rate, capacity remaining)
                limit 1-3
4. Insert lead with source='agrodesk_guide', consent_id, routing_record.
5. Start the routing SLA timer (default 4h business hours per dealer tier).
```

**SLA timer** is a Celery scheduled task per lead. On timeout:
- Mark this dealer as `re_routed`.
- Pick the next candidate from the ranked list, reset the timer, insert a new lead for them (same consent).
- Notify the original dealer so they stop working it.
- Cap total re-routes at 3; after that, route to a "support wait list" with a note to the farmer.

**Anti-abuse** (brief LR-7): rate-limit per phone, detect test / repeat / spoofed numbers via Lookup v2-style checks before the consent prompt.

### 3.4 Community feed — typed posts + locality-first ranking

Instead of free-form status updates, every community row is a **typed post** so moderation, matching and summaries can act on it safely:

```
posts(
  id, account_id, kind, tehsil_id, village_id?, language,
  body_text, audio_path?, transcript?, status,  -- draft|published|archived|removed
  tags jsonb,       -- {crop:"soybean", equipment:"rotavator", hp_range:"35-50"}
  expires_at?,
  created_at
)
kinds ∈ {ask, need_equipment, offer_equipment, price_report, scheme_alert,
         experience, used_tractor (links to listings)}
```

**Ranking** (per feed page load):
```
1. Narrow to tehsil_id ∈ {viewer_tehsil} ∪ neighbours(viewer_tehsil)
2. Filter by the feed tab's kind set.
3. Sort by composite = 0.6·locality_score + 0.3·recency_score + 0.1·helpfulness_score
   locality_score = 1.0 if viewer_village = post_village,
                    0.7 if same tehsil,
                    0.4 if neighbour tehsil,
                    0.1 district only
4. Paged; 20 per page.
5. If the first page has < N items, widen to district.
```

Cached in Redis per (tehsil_id, tab, page), 60 s TTL, invalidated when a new post is created in that tehsil.

**"Helpful" instead of likes.** No visible count below a threshold (say 10) so early posts don't show "0 helpful" and start a pile-on of silence. Weight by expert confirmation.

**Voice posts:**
```
Record (30-90 s, compressed Opus) → upload to object storage →
  STT provider Protocol (adapter, Fake for dev) → transcript + confidence →
  tag extractor (crop, equipment, problem) via a small LLM call →
  present transcript to the poster to edit → publish.
```
Transcript is first-class: search indexes it, moderator agent reads it, readers can play audio or read text. Compressed audio and 10s-step playback speed in the player.

**Why typed posts now:** community is the hardest-to-moderate surface we're building. If every post is a free-text wall, the moderation agent has to infer intent to decide risk. With kinds, "need equipment" posts never need to be scanned for pesticide-dose risks; "ask" posts always do. Cheaper classifiers + sharper guardrails.

### 3.5 Rental exchange — matching + state machine

```
equipment_listings(id, account_id, kind, hp?, rate, rate_unit,
                   service_area jsonb, operator_included, fuel_policy,
                   availability jsonb, media, status)
rental_requests(id, account_id, equipment_kind, acreage, dates, village_id,
                 budget, voice_path?, transcript?, status)
rental_events(id, listing_id, request_id, state, actor, at, note)
ratings(id, rental_event_id, from_profile_id, to_profile_id, score, text)
```

**State machine** (`rental_events.state`):
```
requested → agreed → in_progress → completed_by_both → rated
                                          ↓
                                    disputed → resolved
```

**Matching worker** (Celery task on insert of a new need):
```
1. Search `equipment_listings` where kind matches, availability covers the dates,
   service_area covers the village.
2. For each matched owner, build a WA template send (capped: ≤ 1 per owner per day
   across all needs, soft-limit per week).
3. Owner responds in the thread; masked contact (phone revealed only after both tap "share").
4. On both-sided "completed" confirm, create a `ratings` row request for each side.
```

**Masked contact** = a WhatsApp relay thread anchored on a conversation `thread_id`. Real numbers unmasked only after both sides tap "share number" in the thread.

**Trust gate for rating**: `ratings` insertion requires `rental_events.state in (completed_by_both, rated)`. No rating without completion. Enforced in the service **and** as a trigger on the `ratings` table.

### 3.6 Subsidy — rules engine, not LLM memory

This is the single hardest-to-get-right agent-adjacent surface. The decision in the brief is clear: **rules are structured data; the LLM only asks questions and explains the result.**

```
subsidy_schemes(id, state, title, benefit_summary_mr/hi/en, source_url,
                 last_verified_at, reviewed_by_profile_id, status)
subsidy_rules(id, scheme_id, rule_json, valid_from, valid_till)
subsidy_documents(id, scheme_id, label, required bool, note)
subsidy_steps(id, scheme_id, order, text_mr/hi/en, source_url, note)
subsidy_applications(id, farmer_profile_id, scheme_id, state, started_at, …)
application_events(id, application_id, type, payload, actor, at)
```

**Rule DSL** — JSON Logic-ish, stored per scheme, evaluated by a Python interpreter. Minimal grammar:
```json
{
  "all": [
    { "land_acres": { "lte": 5 } },
    { "category": { "in": ["SC", "ST", "OBC"] } },
    { "owns_tractor_last_years": { "gte": 5 } },
    { "tractor_hp": { "between": [15, 60] } },
    { "dealer_type": { "eq": "verified_agrodesk" } },
    { "state": { "eq": "MH" } },
    { "within": { "field": "deadline", "today": true } }
  ]
}
```

**Review workflow**: a scheme cannot be published until a named human reviewer (KVK / agri officer / verified expert) signs it off. `subsidy_schemes.status` = `draft | in_review | published | outdated`. A nightly job flips schemes past `last_verified_at + 60 days` to `outdated` and hides them.

**Eligibility checker service** returns one of:
- `likely_eligible` + list of matched rules
- `not_eligible` + list of failing rules in the farmer's language
- `need_more_info` + the smallest set of questions to ask next

The LLM is only used to (a) phrase questions in Marathi/Hindi/English and (b) explain `not_eligible` reasons gently. Tools: `evaluate_rules(scheme_id, profile_answers)`, `next_question(...)`. The LLM never has `is_eligible` as a tool; eligibility is a pure function of rules + answers.

**Application tracker** (`application_events`) is farmer-updated: states `applied`, `documents_verified`, `sanctioned`, `paid`. Each advance writes an event and reschedules the reminder cadence. Portal auto-pulling is only wired in if an official API exists (open decision L.3-5).

### 3.7 Trust signals — deterministic, not learned

Trust is **computed by code**, from confirmed events only. No learned scores.

```
trust_signals(profile_id, kind, value, updated_at)
kinds ∈ {completed_rentals, confirmed_sales, confirmed_services,
         helpful_answers_weighted, account_age_days, response_rate_30d,
         verified_badges jsonb}

badges(profile_id, badge, awarded_at, awarded_by)
```

**Rules** (short list, all deterministic):
- `completed_rentals`: COUNT of `rental_events.state='completed_by_both'` over last 365 days.
- `confirmed_sales`: COUNT of `leads.stage='won'` where the farmer's account matches the lead's customer.
- `helpful_answers_weighted`: SUM of `helpful_marks` on this profile's `replies`, weight 1 by default, 3 if the reply is `expert_confirmed`.
- `response_rate_30d`: % of inbound messages with a reply within 24 h over the trailing 30 days.
- `account_age_days`: just time.

**Badges** (not numbers, to prevent gaming by competition):
- `verified_dealer` (verification flow pass)
- `verified_expert` (expert application + admin pass)
- `trusted_renter` (≥ 5 completed rentals + no open disputes)
- `trusted_seller` (≥ 3 confirmed sales + no open disputes)

**Anti-gaming** (brief RP-4): exclude ratings from accounts <7 days old; detect rating rings by graph analysis (accounts repeatedly rating each other); require two-sided completion for any rental rating. Runs as a daily job that reviews the preceding day's new ratings and flags suspicious clusters for admin review.

### 3.8 Moderation pipeline — pre-screen + human queue

Every piece of user-generated content (posts, replies, listings, rental events, voice transcripts) goes through:

```
Content submitted
     ↓
Moderator agent (code + LLM-assist) → one of:
   APPROVE          → publish
   FLAG + reason    → status=in_review, publish=false, queue for human
   BLOCK + reason   → status=removed, notify poster with reason
     ↓
Human queue (admin PWA) with SLA tag (24h default)
  Actions: approve / edit / remove / warn / suspend
     ↓
Audit log; appeal path (phase v2.3)
```

**Pre-screen rules** (code, not LLM) run first — fastest and most reliable:
- blocklist of banned words / phrases (abuse, scams, slurs)
- regex for phone numbers in body (we mask contact until both agree)
- rate-limit per poster per hour (anti-spam)

**LLM-assisted classifier** runs second, only on content that passes the pre-screen. Returns `{risk_category, confidence, suggested_action}`. `low confidence` → always queued, never auto-blocked.

**Why both:** code catches cheap known-bad quickly; the LLM handles novel abuse. The code layer is a hard floor if the LLM provider is down.

### 3.9 Expert Q&A — queue + AI-drafted answers

```
expert_profiles(id, account_id, credentials_url, verified_at, verified_by)
expert_queues(id, scope jsonb)  -- {crops:[...], topics:[...], tehsils:[...]}
questions(id, post_id, queue_id, routed_at, due_at, answered_at)
answers(id, question_id, draft_text, approved_by, approved_at, is_pinned)
```

Workflow:
1. A community `ask` post with no reply after 24 h is auto-routed to the queue whose scope matches its tags.
2. The **expert-draft agent** writes a draft answer from approved KB sources (shared catalogue + scheme KB only — never a competing dealer's private KB). Labelled `AI draft`.
3. Expert reviews on the Expert PWA, approves or corrects.
4. On approve, the answer is published as a reply on the original post, marked `expert_confirmed`, pinned to the top. Trust signals on the expert update.

**Hard guardrail:** no pesticide / chemical dosage, no medical guidance — regardless of what the draft says, these categories require an explicit "verified by an agriculture officer" mark and a linked source, else the answer is blocked at submit time.

### 3.10 Voice — STT/TTS adapter pattern

Reuse the same shape as the WhatsApp / embedding adapters:
```python
class SttProvider(Protocol):
    name: str
    async def transcribe(self, audio: bytes, mime: str, hint_lang: str) -> Transcript: ...
class TtsProvider(Protocol):
    name: str
    async def synthesize(self, text: str, lang: str, voice: str) -> AudioBytes: ...
```

Dev: `FakeSttProvider` returns the filename stem as the transcript so tests can assert flow without external calls.
Prod: a provider tested on Marathi dialects (Sarvam, Bhashini, ElevenLabs, OpenAI — all open decisions).

---

## 4. Scale and reliability

### 4.1 Load estimates (sanity check)

**Pilot (1 tehsil, 5 dealers, 50 farmers)**:
- Leads: ~3 / day across all dealers.
- Community posts: ~5-10 / day, all from this tehsil.
- Rental needs: ~1-2 / week.
- Voice posts: ~1-3 / day, each ≤ 90 s.
- Daily STT seconds: ~300 s. At ~$0.006 / s hosted ≈ $1.80 / day pilot-wide.

**Design-for (1 state, 200 dealers, 50k farmers)**:
- Community posts: 200 posts/day/tehsil * (say) 50 active tehsils = 10k/day.
- Voice minutes: ~25% of posts = 2500/day * 60s = 150k s/day. STT cost ~$900/day if run naïvely. **Needs careful caching + silence trimming + a cheaper real-time model**; call out as a scaling trigger.
- Rentals: 100/day across the state.
- Subsidy checks: 500/day.
- LLM calls (Shivar, moderation drafts, expert drafts): ~20k/day, ~$30/day on a cheap default model.

None of this is hard-scale on the storage side. The expensive hinge is **STT cost** and **LLM cost under the farmer-side fan-out**.

### 4.2 Horizontal scaling plan
- API stateless, N replicas behind a load balancer.
- Celery pools split by shape: `agents` (LLM-bound, low concurrency), `senders` (I/O, higher concurrency), `stt` (long jobs, separate queue, limited concurrency per vendor QPS).
- Postgres: single primary at pilot, read replica for `community.feed` and the admin dashboard when the primary starts to twitch (~50 active dealers).
- Redis: single managed node is fine.
- **One Celery beat** (the standard constraint). Fine at pilot and for v2.x.

### 4.3 Failover + degraded modes
- STT provider down → still accept voice posts; queue transcription; post visible with "(transcribing…)".
- LLM provider down → all AI draft steps queue; human-only moderation; Mitra posts a short template reply explaining the delay.
- WhatsApp BSP down → outbox retries; farmers see a "will sync" badge on queued posts/replies (we already built the client-side piece for Quick Add in E3.1).
- Moderation human queue overflowing → pause automatic publish of non-essential types (experience posts) first, then reduce routing to experts, finally pause all farmer posting with a banner.

### 4.4 Monitoring + alerting
| Signal | Threshold |
|---|---|
| Mitra first-reply SLO | p95 > 5 min in business hours |
| Lead-routing SLA re-routes | > 20% of leads in 24 h |
| Moderation queue depth | > 50 or oldest > 4 h |
| STT backlog | > 30 in queue or p95 > 60 s |
| Rental-match alerts sent / owner-opt-in violations | > 0 |
| Expert queue oldest item | > 20 h (approaching 24 h SLA) |
| Subsidy "outdated" count at service start | > 0 (schemes auto-hidden, admin must refresh) |
| Agent guard-trip rate per agent | > 10% / h |
| LLM + STT daily cost | > 150% of 30-day average |

---

## 5. Trade-offs — decisions made

| # | Decision | Alternative | Why we chose it | When to revisit |
|---|---|---|---|---|
| 1 | One account, many profiles | Separate accounts per role | Phones are the identity; a dealer who also farms must not re-enter their number. Profile switcher on each surface. | Only if a profile ever needs legally-distinct contracts that must stay apart. |
| 2 | Tehsil + neighbour map, **not** PostGIS | PostGIS point-in-polygon on live coords | Farmer location is village-level; "near me" is administrative, not Euclidean. Neighbours map is tiny, cached, and human-reviewable. | If we ever need a true distance filter (e.g. show offers within 10 km of a point the farmer explicitly shared). |
| 3 | Typed posts, not free-text | Free-text status feed | Typed posts let moderation, matching, and summaries use cheap classifiers instead of trying to infer intent every time. | If a kind is missing enough that users hack around it (we've seen "Ask" being used for Prices etc.) — add a kind, don't go free-text. |
| 4 | Subsidy = rules-as-data, LLM for phrasing | LLM-only eligibility | Government schemes are pass/fail by rule; an LLM "ruling" is unsafe. Humans encode rules, LLM only asks and explains. | Never for eligibility itself. LLMs can still help authors turn scheme text into rule JSON faster. |
| 5 | Deterministic trust signals + badges | Learned reputation score | Learnt scores can be gamed and can't be audited. Badges are explainable and contest-poor (no public leaderboard to compete on). | If activity volume makes badges too easy to earn, add thresholds; if they're too hard, lower thresholds. Never add a public score. |
| 6 | Voice posts: audio **and** transcript, both first class | Audio only; transcript-only | Audio preserves nuance; transcript enables search, moderation, agent handling, and accessibility. Costs more storage; worth it. | Transcript-only for languages where STT is reliable enough that users rarely re-open the audio. |
| 7 | Two-layer moderation (code pre-screen + LLM classifier) | LLM only | Code pre-screen catches scams, phone numbers, abuse at ~5ms; LLM handles the long tail. Keep the floor even if LLM is down. | Never single-layer. |
| 8 | Expert queue separate from community agents | One big agent | Experts need an auditable record of what they approved. Keep AI draft + expert approve as two steps, not a hidden transformation. | Never merge. If drafts get boringly good, auto-publish and let the expert "review within 1 h" — but still audit the delta. |
| 9 | Masked contact everywhere (rentals + marketplace) | Show phone immediately | Protects both sides; makes it easier to later charge for intros or add payments without changing the UX. | Never, except for a dealer's own listed business number (public already). |
| 10 | Dealer verification before farmer leads reach them | Dealers can receive leads immediately | A farmer trusts us when we route them; routing to unverified dealers breaks that trust. Verification is a one-time admin step. | Never. |
| 11 | Scheme content requires named human reviewer | Trust LLM extraction | Legal exposure + farmer impact is too high. Named reviewer is also a social accountability check on our review loop. | Never. |
| 12 | Tehsil-by-tehsil rollout | Nationwide switch-on | Every tehsil needs seeded dealers, an expert partner, and moderation coverage in the local language. One tehsil pilot proves the ratio. | Never. Scale is a product + partnerships job, not a flag flip. |

---

## 6. What we'd revisit as the system grows

| Trigger | Change |
|---|---|
| > 50 active tehsils | Read replica for community feed, push caches to Redis. Shard moderation queue by region. |
| > 200k voice minutes / month | Negotiate a committed-use STT contract; add silence trimming + VAD pre-processing to cut 20-30% before sending. |
| > 10k posts / tehsil | Move the "Near me" ranking into a materialized view refreshed every minute + expire-on-new-post invalidation. |
| Moderation SLA slipping | Add trusted-local-moderator tier (brief MD-3), one per tehsil, scoped to their tehsil. Human cost per tehsil drops. |
| A dealer group wants isolation | Move them to a dedicated DB. The RLS seam makes this cheap. |
| STT cost dominates | Fine-tune a small on-prem Indic STT model, run it in a worker fleet; fall back to vendor only for low-confidence re-transcribes. |
| Expert queues sitting idle in some tehsils | Open cross-tehsil routing for those crops/topics; keep hyper-local for the ones with coverage. |
| A single KB crosses 10k chunks | pgvector IVFFlat index (brief Part F.5 switch plan). |

---

## 7. Assumptions (flag if any of these turn out wrong)

1. Village-level location is enough for the pilot. We never need exact coordinates for matching.
2. WhatsApp templates can carry Marathi + Hindi well within 160-char tier pricing. (We should verify before writing the full template catalog.)
3. Indic STT accuracy on Marathi varieties in Nashik district is ≥ 80% word accuracy on clean audio. **Must benchmark before the voice community goes live.**
4. One agriculture expert partner covering the pilot tehsil can clear the Q&A queue within 24 h for the first 30-50 active farmers.
5. Dealers will accept a 4-hour SLA before re-routing. (Pilot-tune: longer or shorter per tier.)
6. Subsidy rule authors produce ~2 schemes / week after a two-week ramp. If less, scope the first scheme library to 2 schemes and expand slowly.
7. Legal review clears: 18+ gate via DOB+OTP, rental terms as a non-party intermediary, voice-recording consent copy. If any fails, the gated features stay dark until the copy or the process is amended.

---

## 8. What this doc does **not** cover
- Detailed per-feature schemas (those live in Alembic migrations and `AGRODESK_FINAL_APP_FEATURES.md` Part 9).
- Pricing, cost-per-conversation modelling (needs the pilot's actual mix).
- Biocred — gated per brief Part 5.13; no engineering until a buyer and verification partner commit.
- Y3+ ideas (parts commerce, insurance referrals) — only if earlier phases pull.

---

_Change log: 2026-11-22 — first version to match `AGRODESK_FINAL_APP_FEATURES.md`. Supersedes v1 doc on everything two-sided. Update alongside DECISIONS.md whenever any numbered trade-off in §5 changes._
