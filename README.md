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
| [`ENGINEERING_DECISIONS.md`](ENGINEERING_DECISIONS.md) | Key decisions and trade-offs |
| [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) | What is intentionally missing |
| [`docs/SYSTEM_DESIGN.md`](docs/SYSTEM_DESIGN.md) | Architecture, patterns, errors, security, scaling |
| [`docs/DATA_MODEL.md`](docs/DATA_MODEL.md) | Collections and indexes |
| [`docs/API_SPEC.md`](docs/API_SPEC.md) | API contract |
| [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) | Risk-driven test strategy |

## Quick start (fill after implementation)

### Prerequisites
Docker and Docker Compose. Nothing else is required for the local path.

### Option A: Local database (no accounts needed)
```bash
cp .env.example .env          # defaults work for the local profile
make up-local                 # api, worker, web, proxy, mongodb-atlas-local
make indexes                  # creates regular indexes and Atlas Search/Vector indexes
make seed                     # demo users, teams, ~300 items with history
open http://localhost:8080
```

### Option B: MongoDB Atlas
```bash
cp .env.example .env
# set MONGODB_URI to your Atlas connection string (replica set, transactions enabled)
make up
make indexes && make seed
```

### Optional AI configuration
- Embeddings run locally (no key needed).
- To enable answer synthesis in "Ask the history", set `ANTHROPIC_API_KEY` and `LLM_MODEL` in `.env`. Without a key the feature returns the relevant passages with no generated answer.
- Set `AI_ENABLED=false` to disable the AI layer entirely. The rest of the app is unaffected.

## Demo accounts (development only)
*(fill after seeding: list email, role and teams for each, for example one viewer, one member, one lead, one org admin, and one user who belongs to two teams with different roles.)*

## Try the critical behaviours (fill after implementation)
1. **Claim race:** sign in as two users in two browsers, open the same unassigned item, click *Claim* on both. One wins, the other sees who won.
2. **Stale edit:** open an item in two browsers, change priority in one, then save a description edit in the other. The second sees a conflict dialog with the changes.
3. **Retry safety:** create an item, then replay the request with the same `Idempotency-Key` (see `docs/API_SPEC.md` §6). No duplicate appears.
4. **Async failure:** stop the worker, perform actions, restart it. Notifications and search/embedding updates catch up (`/admin/outbox`).
5. **Authorization:** sign in as a viewer or as a user from another team and try the same item.
6. **AI:** create an item resembling an existing one and see the similar-items hint. Ask "why did we change the refund approval rule?" on the Ask page.

## Running tests
```bash
make test        # unit + integration (starts atlas-local)
make eval        # retrieval evaluation, writes eval/results/latest.md
make explain     # index usage report on the seeded dataset
```
Integration tests run against a real MongoDB because concurrency and transaction behaviour cannot be verified with mocks.

## Project layout
See `docs/SYSTEM_DESIGN.md` §4 and §8.4.

## Notes on performance testing
Atlas free clusters limit throughput (about 100 operations/second) and are not representative for load tests. Load numbers in this repo were measured against the local stack. *(fill after the run)*

## Known limitations
See [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
