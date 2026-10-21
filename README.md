# Opsboard: Operations Under Pressure

An internal web application for coordinating operational work: requests, incidents, approvals and their history. Built for the Newtonite Software Engineering Challenge.

**Stack:** FastAPI (Python 3.12) · MongoDB Atlas (transactions, Atlas Search, Atlas Vector Search) · Next.js · TanStack Query · Tailwind. A worker process handles asynchronous work through a transactional outbox.

> This README is a template. Sections marked **(fill after implementation)** must be completed and verified on a fresh clone before submission.

## What it demonstrates

| Critical behaviour | How |
|---|---|
| Two people claim the same work | Atomic compare-and-set, one winner, the loser gets `409` naming the winner |
| Stale information | `ETag` / `If-Match` optimistic locking, `412` with the current state and changes since |
| Repeated actions | `Idempotency-Key` stored in the same transaction as the action |
| Reliable async processing | Transactional outbox, leases, backoff, dead-letter, idempotent handlers |
| Resource-level authorization | One pure policy, per-team roles, 404 for invisible resources, four-eyes approvals |
| Optimistic UI vs server truth | Rollback and conflict dialog driven by typed error codes |
| AI/RAG (optional layer) | Similar-item hints and a grounded "Ask the history", authorization-filtered, with citations and graceful degradation |

## Documentation

| Doc | Contents |
|---|---|
| Doc | Contents |
|---|---|
| [`docs/ENGINEERING_DECISIONS.md`](docs/ENGINEERING_DECISIONS.md) | Key decisions and trade-offs |
| [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md) | What is intentionally missing |
| [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) | Architecture, patterns, errors, security, scaling |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Collections and indexes |
| [`docs/API_SPEC.md`](docs/API_SPEC.md) | API contract |
| [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) | Risk-driven test strategy |

## Quick start

### Prerequisites
Docker and Docker Compose (or local Python 3.12, Node.js 20, MongoDB replica set).

### Option A: Local database (no accounts needed)
```bash
cp .env.example .env          # defaults work for the local profile
make up-local                 # api, worker, web, proxy, mongodb-atlas-local
make indexes                  # creates regular indexes and Atlas Search/Vector indexes
make seed                     # demo users, teams, items with history across 6 categories
open http://localhost:3000
```

### Option B: MongoDB Atlas
```bash
cp .env.example .env
# set MONGODB_URI to your Atlas connection string (replica set, transactions enabled)
make up
make indexes && make seed
```

### Optional AI configuration
- Embeddings and retrieval run with pluggable providers (`fake`, `fastembed`, `openai`).
- To enable answer synthesis in "Ask the history", set `ANTHROPIC_API_KEY` (or `OPENAI_API_KEY`) and `LLM_MODEL` in `.env`. Without a key the feature returns the relevant passages with no generated answer.
- Set `AI_ENABLED=false` to disable the AI layer entirely. The rest of the app is unaffected.

## Demo accounts (seeded for development & evaluation)

All accounts share the password `Password123!`.

| User | Email | Role & Team Memberships | Demo Purpose |
|---|---|---|---|
| **Alice Admin** | `admin@opsboard.dev` | Org Admin (Global cross-team access) | Cross-team visibility, system monitoring |
| **Priya Lead** | `lead@opsboard.dev` | Payments (Lead), Compliance (Lead), Engineering (Member) | Four-eyes approval decisions, multi-team membership |
| **Marcus Member** | `member@opsboard.dev` | Payments (Member), Engineering (Lead) | Item claim, requesting approvals, lead transitions |
| **Sarah Contender** | `member2@opsboard.dev` | Payments (Member) | Claim race competitor, concurrent edit conflicts |
| **Victor Viewer** | `viewer@opsboard.dev` | Payments (Viewer) | Read-only enforcement (cannot claim or mutate) |

## Try the critical behaviours
1. **Claim race:** sign in as two users (`member@opsboard.dev` and `member2@opsboard.dev`) in two browser sessions, open unassigned item `PAY-101`, click *Claim* on both. One wins, the other receives `409 Conflict` identifying the winner.
2. **Stale edit:** open item `PAY-103` in two windows, change priority in one, then save a description edit in the other. The second sees a conflict dialog with `412 Precondition Failed` detailing concurrent changes.
3. **Retry safety:** create an item, then replay the request with the same `Idempotency-Key` (see `docs/API_SPEC.md` §6). The exact same item is returned without duplicate records.
4. **Async failure:** stop the outbox worker (`make down` or kill worker), perform mutations, restart worker. Notifications and search indexes catch up via transactional outbox.
5. **Authorization:** sign in as `viewer@opsboard.dev` and attempt to claim or edit; verify `403 Forbidden` / disabled controls. Try accessing another team's private items as a member without membership; verify clean `404 Not Found`.
6. **AI:** ask "What customer was double charged on checkout?" on the Ask page or search items. View citation provenance and similarity scores.

## Running tests
```bash
make test        # unit + integration (runs against MongoDB)
make eval        # retrieval evaluation, writes eval/results/latest.md
make explain     # index usage report on the seeded dataset
make check       # full verification: test + explain + eval
```
Integration tests run against real MongoDB because concurrency and transaction behaviour cannot be verified with mocks.

## Project layout
See `docs/SYSTEM_DESIGN.md` §4 and §8.4.

## Notes on performance testing
Atlas free clusters limit throughput (about 100 operations/second) and are not representative for load tests. Load numbers in this repo were measured against the local replica set with zero COLLSCAN operations verified by `make explain`.

## Known limitations
See [`docs/KNOWN_LIMITATIONS.md`](docs/KNOWN_LIMITATIONS.md).
