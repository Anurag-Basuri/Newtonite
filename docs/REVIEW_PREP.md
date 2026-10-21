# Review Preparation

The brief says you may be asked to explain or modify any part of the system, and that reasoning matters as much as features. This is your rehearsal sheet.

## 1. Demo script (≈10 minutes)

| Min | Show | Say |
|---|---|---|
| 0–1 | Overview page as a lead | "This answers *what needs attention*: approvals waiting on me, overdue, urgent-unowned, stale. Each bucket is an indexed query, not a scan." |
| 1–2 | Items list: filter by status and team, scroll, then ⌘K search | "Keyset pagination, filters in the URL, search on Atlas Search. Nothing is loaded wholesale into the browser." |
| 2–4 | **Claim race**: two browsers, two users, click Claim together | "One compare-and-set on the item document inside a transaction. The loser gets 409 naming the winner, and the UI rolls back its optimistic state." |
| 4–5 | **Stale edit**: edit in both browsers, save the older one | "ETag and If-Match. The 412 carries the current item and the events since my version, so the dialog shows exactly what changed." |
| 5–6 | **Retry safety**: replay a create with the same key (curl) | "The idempotency record commits in the same transaction as the item, so there is no window where one exists without the other." |
| 6–7 | Item timeline and approvals (four-eyes) | "History is append-only events. The approval decision is a compare-and-set, and a requester cannot approve their own request." |
| 7–8 | Stop the worker, act, restart | "Outbox: the work was durably recorded with the state change. Leases, backoff and dead-letter handle failure. Handlers are idempotent." |
| 8–9 | Similar-items hint and Ask the history (as a user in one team, then another) | "Retrieval is pre-filtered by team, so another team's text never reaches the prompt. Citations are validated. Without the LLM it degrades to passages." |
| 9–10 | Tests, explain output, eval report | "These are the tests for the dangerous cases. Here is the proof the queries use indexes, and the retrieval metrics." |

## 2. "What happens when X fails?"

| Failure | Behaviour | Where to point |
|---|---|---|
| Two users claim at once | One `200`, one `409 ALREADY_CLAIMED` | SYSTEM_DESIGN §6.1, T-CLM-1 |
| Stale edit | `412` with current state and changes since | §6.2, T-VER-1 |
| Client times out and retries | Same key replays the stored response | §6.3, T-IDM-1/2 |
| API crashes mid-request | Transaction aborts: no item, no event, no outbox, no key. Retry re-executes cleanly | T-TXN-1 |
| Worker crashes mid-job | Lease expires, another worker reclaims | §6.4, T-OBX-4 |
| Handler fails repeatedly | Backoff, then `dead`, visible to admins and retryable | T-OBX-2/7 |
| Handler runs twice | Unique `dedupe_key` and deterministic chunk ids, so no duplicates | T-OBX-3, T-AI-7 |
| Worker down for an hour | Core app unaffected. Notifications and embeddings lag, then catch up | T-OBX-8 |
| Mongo primary election during a request | Driver retries transient errors, transaction callback re-runs, idempotent by design | `uow.py` |
| Atlas Search unavailable | Fallback to bounded prefix match, flagged as degraded | §7.3 |
| Change streams unavailable | SSE hub polls `item_events` | §7.6 |
| LLM down, slow or no key | `degraded: true` with retrieved passages, circuit breaker | §9.5, T-AI-4 |
| User removed from a team | Next request returns 404. SSE and RAG filters use current memberships | T-AZ-7 |
| Dead-letter queue grows | `/admin/outbox` shows depth and age | §14 |

## 3. Likely "please change this live" requests, and where to change them

| Request | Change | Files |
|---|---|---|
| Add a new status (e.g. `on_hold`) | Add a row to the transition table and the enum, update indexes only if filtered | `domain/workflow.py`, `enums.py`, tests T-WF-1 |
| Make members able to triage | Edit one policy rule | `domain/policy.py`, matrix test |
| Add a priority P4 or change SLA windows | Enum plus `domain/attention.py` | |
| Require approval for all P0 items | Default in item creation service | `modules/items/service.py` |
| New attention bucket | Query plus bucket definition. Add an index if needed | `modules/overview`, DATA_MODEL |
| Change the retry or backoff policy | Constants in the outbox module | `infra/outbox.py` |
| Swap the embedding model | Provider config and re-index (`/admin/reindex`) | `modules/ai/embedder.py` |
| Add a notification type | New recipient rule in the notify handler | `worker/handlers/notify.py` |
| Add a field to items | Schema, repo projection, API spec, event diff, UI form | multiple, follow the layering |
| Soft-delete or archive | Terminal `archived` flag plus partial index exclusion | |

## 4. "What would you change at 10× scale?"

1. Move SSE fan-out to a dedicated gateway or pub/sub (per-instance change streams stop scaling with replicas).
2. Dedicated Atlas Search Nodes, a larger tier, and `secondaryPreferred` reads for lists and search.
3. Shard `item_events` and `item_chunks` on hashed `item_id`, and archive old history.
4. Split outbox handlers into separate queues and worker pools (notify vs embed). Replace polling with a broker if latency demands it.
5. Replace `teams.item_counter` with ULID-based keys if creation rate per team becomes a bottleneck.
6. Add per-tenant rate limiting and quotas on AI usage, and cache embeddings for repeated queries.
7. Observability: metrics, tracing across API to outbox to worker via `correlation_id`, SLO alerts.

## 5. "What next with another week?"

1. Hybrid retrieval (vector + lexical with RRF) and a reranker, measured with the golden set.
2. Playwright end-to-end race tests and a CI load test with latency budgets.
3. Configurable workflows per team, SLA policies per team, and escalation notifications when work goes stale.
4. Real email and Slack delivery as outbox handlers.
5. SSO and MFA, plus an audit-log viewer.
6. Cross-team transfer with an approval handshake.
7. Streaming AI answers, and "summarise this item's timeline" and triage suggestions.
8. Comment edit/delete modelled as events (`comment.edited`) to preserve append-only history.

## 6. Questions you should be ready to answer crisply

- **Why MongoDB for something this relational?** It was the requirement. I used it carefully: single-document atomicity for the hot invariants, transactions only where several writes must agree, and unique and partial indexes for constraints. Atlas also gave search and vectors in one system. In a free choice I'd weigh Postgres.
- **Why not just use transactions everywhere?** They cost latency and conflicts. The claim, version check and approval decision are single-document conditional updates. Transactions are used where state, event, outbox and idempotency record must commit together.
- **Is exactly-once real?** No. It is at-least-once delivery plus idempotent consumers, which gives effectively-once effects.
- **Why a 404 instead of 403?** To avoid revealing that a resource exists to someone who cannot see it.
- **Why are comments not bumping `version`?** So conversation never invalidates someone's edit. `event_seq` orders the timeline.
- **Why SSE hints rather than pushing data?** One source of truth and one authorization path. The cost is one refetch.
- **How do you stop the AI leaking another team's data?** Pre-filter by team in `$vectorSearch`, post-retrieval policy re-check, the LLM has no tools, and a test asserts the foreign secret never reaches the prompt (T-AI-1).
- **How do you know retrieval is any good?** The golden-set evaluation reports Recall@k, MRR and citation validity. Chunking and thresholds were tuned against it.
- **Why not LangChain or LlamaIndex directly?** The challenge requires total control over authorization boundaries, concurrency, and validation. In ~200 lines of explicit code, we implement custom semantic chunking, MongoDB `$vectorSearch` pre-filtered by `team_id`, and server-side citation validation without heavy dependencies. We decoupled everything behind `EmbeddingProvider` and `LLMProvider` interfaces—making it trivial to integrate LangChain/LlamaIndex retrievers later if scaling to external multi-source connectors.
- **What is the weakest part of the system?** Be candid: polling outbox latency, per-instance SSE, small embedding model quality, and the free-tier limits for load testing. All are in KNOWN_LIMITATIONS with a growth path.
