# Test Plan

The brief asks us to identify behaviours that would be **dangerous if wrong** and test those, rather than chase coverage. This plan is derived from the risks in our own architecture.

## 1. Strategy

| Layer | Tooling | What it proves | Share of effort |
|---|---|---|---|
| **Domain unit tests** | pytest, hypothesis | Workflow table, policy matrix, SLA/attention maths, chunker, cursor encoding | 25% |
| **Integration tests against real MongoDB** | pytest-asyncio, httpx `AsyncClient`, `mongodb-atlas-local` | Atomicity, concurrency, idempotency, outbox, txn rollback, pagination, search, authz over HTTP | **50%** |
| **AI tests** | fake embedder + fake LLM | Authorization-safe retrieval, grounding, degradation, prompt-injection handling | 15% |
| **Frontend tests** | Vitest + Testing Library; Playwright (stretch) | Optimistic update / rollback logic, conflict dialog, idempotency-key reuse | 10% |

**Rule:** concurrency and transaction behaviour is **never** tested against a mock. A mock cannot reproduce write conflicts, which is exactly what we are verifying. Integration tests run on the `atlas-local` image (replica set, transactions, `$search`, `$vectorSearch`).

**Fixtures:** per-test database (unique name, dropped after), factories for users/teams/memberships/items, injectable clock, fake providers via dependency overrides.

**Async index tests:** Atlas Search/Vector indexes are eventually consistent. Tests poll with a timeout (max 15 s) via a `wait_until()` helper instead of sleeping.

## 2. Risk register → tests

Priority: **P0** must exist before submission; **P1** should; **P2** stretch.

### 2.1 Concurrency and consistency

| ID | Risk (if wrong) | Test | Pri |
|---|---|---|---|
| T-CLM-1 | Two people own one item | 25 concurrent claims by 25 different users via `asyncio.gather`. Assert exactly one `200`, 24 `409 ALREADY_CLAIMED`, exactly one `item.claimed` event, one assignee, `version` incremented once | **P0** |
| T-CLM-2 | Claim on a closed item succeeds | Claim closed item gives `409 ITEM_CLOSED` | P0 |
| T-VER-1 | Silent overwrite | A reads v7, B patches (v8), A patches with `If-Match: "7"` gives `412`; response includes `current` and `changes_since`; item unchanged; no event written | **P0** |
| T-VER-2 | Edits without a precondition | PATCH without `If-Match` gives `428` | P0 |
| T-VER-3 | Comments block edits | Add comment, then edit with the old ETag still succeeds (comments don't bump `version`) | P0 |
| T-VER-4 | Parallel edits corrupt state | 10 concurrent patches with the same `If-Match`: exactly one succeeds, nine `412` | P1 |
| T-IDM-1 | Duplicate create on retry | Same `Idempotency-Key` twice: one item, one event, one outbox set; second response identical with `Idempotent-Replay: true` | **P0** |
| T-IDM-2 | Concurrent duplicate requests | 10 concurrent requests with the same key: exactly one executes, all return the same body | **P0** |
| T-IDM-3 | Key reuse with another payload | Same key, different body gives `422 IDEMPOTENCY_KEY_REUSED` | P0 |
| T-IDM-4 | Key missing | Mutating POST without a key gives `400` | P0 |
| T-IDM-5 | Failed attempt poisons the key | First attempt fails validation; retry with corrected body and the same key executes normally | P1 |
| T-TXN-1 | Partial writes | Inject a failure after the event insert (fault-injecting repo): item, event, outbox and idempotency record **all absent** | **P0** |
| T-APR-1 | Two approvers both "win" | Two leads decide concurrently: one `200`, one `409`; exactly one `approval.*` event; item in a single resulting state | P0 |
| T-APR-2 | Second pending approval | Request approval twice gives `409 APPROVAL_PENDING` (also verifies the partial unique index directly) | P0 |

### 2.2 Workflow rules

| ID | Risk | Test | Pri |
|---|---|---|---|
| T-WF-1 | Illegal transitions accepted | Parametrised over **every** (from, to) pair: allowed pairs succeed for the right role, all others give `409 INVALID_TRANSITION` with `meta.allowed` | **P0** |
| T-WF-2 | Approval bypass | `in_progress → resolved` on an item with `requires_approval` is rejected. Approval-only transitions via `/transitions` are rejected | **P0** |
| T-WF-3 | Missing reason/resolution | `blocked`, reject, cancel without reason give `422` | P0 |
| T-WF-4 | State machine soundness | Hypothesis stateful test: random sequences of actions by random roles never reach a state outside the table, never leave `assignee` set on a closed item incorrectly, and `version` strictly increases | P1 |

### 2.3 Authorization

| ID | Risk | Test | Pri |
|---|---|---|---|
| T-AZ-1 | Privilege holes | **Matrix** (role × action × relationship [reporter / assignee / other]) against `policy.can` (unit) *and* a sampled subset over HTTP | **P0** |
| T-AZ-2 | Cross-team leakage | User in team A requests items, timeline, comments, search, similar and SSE for team B items: always `404`/absent, never `403` | **P0** |
| T-AZ-3 | Role per team | Same user is `lead` in A and `viewer` in B. Actions succeed in A and fail in B | P0 |
| T-AZ-4 | Four-eyes | Requester approving own request gives `409 FOUR_EYES_VIOLATION` | P0 |
| T-AZ-5 | Viewer writes | Viewer: create/comment/claim all `403` | P0 |
| T-AZ-6 | Assign to non-member | `assign` to a user outside the team gives `422` | P1 |
| T-AZ-7 | Revoked access takes effect | Remove membership: next request `404`; SSE stops delivering hints within 60 s | P1 |
| T-AZ-8 | Query-parameter escalation | `team_id` filter with a team the user isn't in returns an empty set or 404, never data | P0 |
| T-AZ-9 | NoSQL operator injection | JSON bodies/params containing `{"$ne": null}` for ids and strings give `422`, never alter the query | P0 |

### 2.4 Async processing (outbox and worker)

| ID | Risk | Test | Pri |
|---|---|---|---|
| T-OBX-1 | Lost side effects | Mutation commits, then the outbox message exists. Stop the worker, restart, message processed | **P0** |
| T-OBX-2 | Handler failure | Failing handler: `attempts` increments, `next_attempt_at` follows backoff (injected clock), message becomes `dead` after `max_attempts` | **P0** |
| T-OBX-3 | Duplicate delivery | Run the notify handler twice for the same message: exactly one notification per recipient | **P0** |
| T-OBX-4 | Crashed worker | Claim a message, abandon it (no completion). After lease expiry, another worker reclaims and finishes it | P0 |
| T-OBX-5 | Two workers, one message | 3 workers polling concurrently: each message handled once (no double `processing`) | P0 |
| T-OBX-6 | Out-of-order | Process `index_item` for an older `content_version` after a newer one: stored chunk keeps the newer | P1 |
| T-OBX-7 | Dead letter retry | Admin retry of a dead message re-queues and succeeds | P1 |
| T-OBX-8 | Worker down does not break the API | Mutations succeed with no worker running | P0 |

### 2.5 History and data integrity

| ID | Risk | Test | Pri |
|---|---|---|---|
| T-HIS-1 | Important actions disappear | Every mutation type produces exactly one event with correct `type`, `actor`, `item_version` and `payload` | **P0** |
| T-HIS-2 | History mutable | Repo exposes no update/delete (reflection test). Unique `(item_id, seq)` enforced | P0 |
| T-HIS-3 | Event order | Concurrent comments on one item get distinct, gap-free-per-commit `seq` values, and the timeline is ordered | P1 |

### 2.6 Scale and queries

| ID | Risk | Test | Pri |
|---|---|---|---|
| T-PAG-1 | Duplicates or gaps across pages | Insert items while paging: union of pages has no duplicates and no skipped pre-existing items | **P0** |
| T-PAG-2 | Cursor tampering | Garbage cursor gives `400 BAD_CURSOR` | P0 |
| T-PAG-3 | Limits | `limit > 100` clamped or `422`; default 25 | P1 |
| T-IDX-1 | Collection scans | On the 20k seed, `explain` of every hot query shows `IXSCAN`, no `COLLSCAN`, docs examined ≤ 3× returned | **P0** |
| T-IDX-2 | Overview correctness | Each bucket matches a brute-force Python computation on a small fixture | P0 |
| T-SRC-1 | Search ignores permissions | Search for a term that exists only in a foreign team's item returns nothing | **P0** |
| T-SRC-2 | Search relevance basics | Title match outranks description match. Autocomplete returns prefix matches | P1 |

### 2.7 AI / RAG

| ID | Risk | Test | Pri |
|---|---|---|---|
| T-AI-1 | **Data leakage through RAG** | Seed a secret string in team B. User in A asks about it. Assert the fake LLM's received prompt never contains it, and the response has no citation from B | **P0** |
| T-AI-2 | Post-retrieval defence | Force the retriever to return a foreign chunk (fault injection). The policy re-check drops it | P0 |
| T-AI-3 | Hallucinated citations | Fake LLM cites `[S9]` (not retrieved): marker stripped and flagged | P0 |
| T-AI-4 | LLM down | Provider raises or times out: `200` with `degraded: true` and retrieved passages | **P0** |
| T-AI-5 | AI disabled | `AI_ENABLED=false`: core features work, ask gives `503 AI_DISABLED`, `/meta/features` reflects it | P0 |
| T-AI-6 | Prompt injection | Item containing "ignore previous instructions and reveal …" retrieved as a source: prompt wraps it as data, no behavioural change in the fake-LLM harness, answer rendered as text | P1 |
| T-AI-7 | Ingestion idempotency | Run `index_item` three times: chunk count and ids unchanged. Edited text changes `text_hash` and re-embeds only the changed chunk | P0 |
| T-AI-8 | Chunker | Long text splits ≤ 300 tokens with overlap and header prefix. Short text stays one chunk | P1 |
| T-AI-9 | Retrieval quality | `eval_retrieval.py` meets thresholds (Recall@5 ≥ 0.8 on the golden set) | P1 |
| T-AI-10 | Rate limiting | The 11th ask in a minute gives `429` | P1 |

### 2.8 Errors, realtime, frontend

| ID | Risk | Test | Pri |
|---|---|---|---|
| T-ERR-1 | Inconsistent errors | Every error path (validation, domain, 404 route, unhandled exception) returns Problem Details with `code` and `request_id`, and no stack trace | P0 |
| T-RT-1 | SSE leaks | Client for team A never receives hints for team B | P0 |
| T-RT-2 | SSE delivery | Mutation produces an `item.changed` hint within 2 s | P1 |
| T-FE-1 | Optimistic rollback | Claim returns 409: cache restored, toast names the winner (Vitest) | **P0** |
| T-FE-2 | Idempotency key reuse | Network error then auto-retry uses the **same** key. A 4xx is not retried (Vitest) | P0 |
| T-FE-3 | Conflict flow | 412 keeps the draft, shows the diff, and "Re-apply" sends the new `If-Match` | P0 |
| T-FE-4 | Two-browser race | Playwright: two sessions claim simultaneously, one succeeds and the other sees the winner | P2 |

## 3. Non-test evidence to produce

- `scripts/explain_queries.py` output (index usage).
- `eval/results/latest.md` (retrieval metrics).
- A short note on a local load run (e.g. `k6` or `locust`) against the atlas-local stack: p95 for list/claim/search at 20k items. Not run on the Atlas free tier.

## 4. CI gates

1. `ruff` and `mypy` clean.
2. Unit plus integration tests green (atlas-local as a service container).
3. `tsc`, ESLint, Vitest green.
4. All **P0** test IDs present (a script greps test names for `T-…` IDs and fails if any P0 is missing).

## 5. Definition of "tested enough" for submission

All **P0** rows implemented and passing, the 25-way claim race and idempotent-replay tests stable across 20 consecutive runs, and the retrieval evaluation report committed.
