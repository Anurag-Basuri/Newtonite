# Implementation Plan

Goal: submit a system that matches the design, with the P0 behaviours proven by tests. The plan is built so that **scope is what flexes, never quality**. P0 items are done properly, P1/P2 items are the ones that may be dropped, and anything dropped is listed in `KNOWN_LIMITATIONS.md`.

## 1. Day-0 checklist (before any feature code)

Do these first. Each one removes a risk the design depends on.

| # | Task | Verify |
|---|---|---|
| 0.1 | Create the Atlas project and **free cluster**, a database user, and add your IP to the access list | Connection string works from `mongosh` |
| 0.2 | Create the local fallback: run `mongodb/mongodb-atlas-local` | `mongosh` connects, `rs.status()` shows a replica set |
| 0.3 | **Transaction smoke test** (10-line script) on both Atlas and local | Two concurrent transactions on one document: one commits, the other retries |
| 0.4 | **Change stream smoke test** on `item_events` | Insert triggers an event within ~1 s. If it fails on Atlas, enable the polling fallback and note it |
| 0.5 | **Search and vector index smoke test**: create a tiny `$search` and `$vectorSearch` index through `create_search_index`, query it | Both return results on Atlas and local. Record index-build time |
| 0.6 | Obtain an **LLM API key** (optional but recommended) and put it in `.env` | One successful call. Without a key, the app runs in degraded mode |
| 0.7 | Create the Git repo, `.gitignore`, `.env.example`, branch protection off (solo), CI skeleton | First CI run is green |
| 0.8 | Commit these docs, including `AGENTS.md` | |

If 0.3 or 0.5 fails on Atlas, stop and tell me. These are the two assumptions most of the design leans on.

## 2. Repository layout

```
opsboard/
├── README.md  ENGINEERING_DECISIONS.md  KNOWN_LIMITATIONS.md  AGENTS.md
├── docker-compose.yml  Makefile  .env.example  .github/workflows/ci.yml
├── docs/            SYSTEM_DESIGN, DATA_MODEL, API_SPEC, TEST_PLAN, IMPLEMENTATION_PLAN, REVIEW_PREP
├── backend/         (see SYSTEM_DESIGN §4)
├── frontend/        (see SYSTEM_DESIGN §8.4)
├── deploy/          Caddyfile, Dockerfiles
└── eval/            golden_set.json, results/
```

### Makefile targets
`make up` · `make up-local` · `make down` · `make seed` · `make seed-load` · `make indexes` · `make test` · `make test-unit` · `make test-int` · `make lint` · `make typecheck` · `make eval` · `make explain` · `make openapi` (regenerates frontend types) · `make check` (lint + typecheck + tests).

### Environment variables (`.env.example`)

| Var | Purpose | Default |
|---|---|---|
| `MONGODB_URI` | Atlas or local connection string | none (required) |
| `MONGODB_DB` | Database name | `opsboard` |
| `MONGO_MAX_POOL` | Pool size per process | `20` |
| `SESSION_SECRET` | Cookie/CSRF signing | none (required) |
| `COOKIE_SECURE` | `true` in production | `false` |
| `APP_ORIGIN` | Allowed origin for CSRF check | `http://localhost:8080` |
| `AI_ENABLED` | Master switch | `true` |
| `EMBEDDING_PROVIDER` | `fastembed` or `fake` | `fastembed` |
| `EMBEDDING_MODEL` | Model id | `BAAI/bge-small-en-v1.5` |
| `LLM_PROVIDER` | `anthropic` or `none` or `fake` | `anthropic` |
| `ANTHROPIC_API_KEY` | LLM key. Empty means retrieval-only | empty |
| `LLM_MODEL` | Model id (configurable, never hard-coded) | set at setup |
| `AI_RATE_LIMIT_PER_MIN` | Asks per user per minute | `10` |
| `WORKER_POLL_INTERVAL_MS` | Outbox poll interval | `1000` |
| `OUTBOX_MAX_ATTEMPTS` | Before dead-letter | `6` |
| `LOG_LEVEL` | | `INFO` |

## 3. Build phases

Time-boxes are estimates for one focused day with AI agents doing the typing and you reviewing. Each phase ends with a **gate**: the listed tests pass and the work is committed. Do not start the next phase on a red gate.

### Phase 1: Foundation (≈1.5 h)

**Build:** backend skeleton, config, logging with request-id, Problem Details error handlers, Mongo client, `ensure_indexes`, `UnitOfWork`, pagination cursor helper, auth (login/logout/me, argon2, sessions), teams/memberships read APIs, seed script (small), Docker Compose (api + local mongo), frontend skeleton (login page, API client, generated types).
**Gate:** login works end to end. `T-ERR-1`. `UnitOfWork` retry smoke test (concurrent transactions). Compose boots from a clean clone.

### Phase 2: Core domain (≈3 h), the heart of the system

Order matters. Write the tests from TEST_PLAN **first** for the pure domain code, then implement.

1. `domain/workflow.py` + `T-WF-1`.
2. `domain/policy.py` + `T-AZ-1` matrix.
3. Items: create, get (ETag), list with filters and keyset pagination, patch with `If-Match`.
4. Events: append on every mutation (same transaction).
5. Claim / release / assign. **Run `T-CLM-1` now** against real Mongo.
6. Transitions and approvals (`T-WF-*`, `T-APR-*`, `T-AZ-4`).
7. Comments and timeline.
8. Idempotency (`infra/idempotency.py`) wrapped around all mutating POSTs (`T-IDM-*`).
9. Overview buckets and attention SLA (`T-IDX-2`).

**Gate:** all P0 tests in §§2.1–2.3 and 2.5–2.6 (except search) green, stable across 20 consecutive runs of the claim race.

### Phase 3: Async + realtime (≈1.5 h)

Outbox enqueue inside transactions, worker (lease, backoff, dead-letter, reclaim), `notify` handler, notifications API, SSE hub (change stream, with polling fallback), admin outbox endpoints.
**Gate:** `T-OBX-*` P0 rows, `T-RT-1`.

### Phase 4: Search + AI/RAG (≈2 h)

`setup_atlas_indexes.py`, Atlas Search endpoint, chunker, embedder interface (+fake), `index_item` handler, vector retrieval with team pre-filter, similar-items, `/ai/ask` with citation validation, degradation, rate limit, `ai_queries` log, golden set and `eval_retrieval.py`.
**Gate:** `T-SRC-1`, `T-AI-1…5`, `T-AI-7`. Eval report generated.

### Phase 5: Frontend (runs **in parallel** with Phases 2–4, ≈4 h total)

Starts as soon as `docs/API_SPEC.md` is frozen (it is). The frontend agent works against the generated OpenAPI types and a mock handler (MSW), then switches to the real API when Phase 2 lands.

Order: app shell and login → items list (filters in URL, infinite scroll) → item detail with timeline → actions (claim, transitions, assign, comment) with the optimistic and conflict flows → overview → notifications and SSE → search palette → AI panels (similar on create form, ask page) → polish (empty/loading/error states, keyboard shortcuts, a11y pass).
**Gate:** `T-FE-1…3`. Manual two-browser race demo works.

### Phase 6: Hardening, docs, submission (≈1.5 h)

`explain_queries.py` evidence and `T-IDX-1`, `seed-load` and local load note, security pass (§12 checklist), README with exact run steps, finalise `ENGINEERING_DECISIONS.md` and `KNOWN_LIMITATIONS.md`, fresh-clone test (`git clone` → `make up-local` → `make seed` → login), record demo walkthrough, tag release.
**Gate:** CI green on a clean clone. The README steps work exactly as written.

### Buffer (≈1 h)

Reserved for the thing that goes wrong. Do not plan features into it.

## 4. Working with AI agents safely

Concurrency and persistence code is where agents produce plausible but subtly wrong results. Process:

1. **Lanes** (parallel agents, separate branches, merge at gates):
   - **Agent A: backend core** (Phases 1–3).
   - **Agent B: frontend** (Phase 5, against API_SPEC and generated types).
   - **Agent C: tests and tooling** (writes the P0 tests from TEST_PLAN *before* A implements, plus CI, seed, eval scripts).
   - **Agent D: AI/RAG** (Phase 4) once Phase 2 is merged.
2. **Every agent reads `AGENTS.md` and the relevant doc first.** Prompts should reference doc sections (for example "implement `POST /items/{item}/claim` exactly as API_SPEC §3.3 and SYSTEM_DESIGN §6.1").
3. **Human review is mandatory** for: `db/uow.py`, `infra/idempotency.py`, `infra/outbox.py`, `domain/policy.py`, `domain/workflow.py`, and all repository functions that use conditional updates. These are the files you will be asked to explain and modify in the review.
4. **Tests before code** for P0 behaviours. A feature without its test is not done.
5. **Small commits** with conventional messages. Never let an agent make a 3,000-line commit you cannot review.
6. **Spec conflicts:** the agent stops and asks. Do not let it silently diverge from the API contract.

## 5. Priority cut line

If time runs short, cut from the bottom. Cutting something means adding it to `KNOWN_LIMITATIONS.md`.

| Tier | Items |
|---|---|
| **P0, must ship** | Items CRUD, workflow, ownership, comments and timeline, approvals, teams/roles/policy, the five critical behaviours, overview, list/filter/pagination, search, notifications (in-app), similar-items and ask (with degradation), P0 tests, README, ENGINEERING_DECISIONS, KNOWN_LIMITATIONS |
| **P1, should ship** | SSE live updates, admin outbox UI/endpoints, retrieval eval report, explain evidence, hypothesis state-machine test, keyboard shortcuts, ⌘K palette |
| **P2, stretch** | Hybrid retrieval (RRF), Playwright race test, Prometheus metrics, live deployment, load-test report, streaming LLM answers |

## 6. Submission checklist

- [ ] Fresh clone runs with the README steps only.
- [ ] `make check` passes. CI green.
- [ ] All P0 test IDs present and passing.
- [ ] `ENGINEERING_DECISIONS.md` (5 decisions), `KNOWN_LIMITATIONS.md`, README, diagrams in `docs/`.
- [ ] Seeded demo accounts documented, covering viewer/member/lead/admin and multi-team.
- [ ] `.env.example` complete. No secrets in Git history.
- [ ] Retrieval eval report and `explain` output committed.
- [ ] Demo script rehearsed (`docs/REVIEW_PREP.md`).
- [ ] App works with `AI_ENABLED=false` and with the worker stopped.

## 7. Open items for you

1. **Live deployment:** yes or no, and which cloud or credits you have. If yes, it is a P2 task after the fresh-clone test passes.
2. **LLM key:** which provider and model you can use for the "Ask" feature (default plan is Anthropic via `LLM_MODEL`).
3. **Product name:** "Opsboard" is a placeholder.
