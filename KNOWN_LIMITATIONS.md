# Known Limitations

This list is deliberate. Each item is a scope decision, a stated trade-off, or something to harden next. Items under "May change before submission" depend on how far the build gets.

## Product scope (intentionally not built)

- **No SSO / OAuth / MFA.** Email and password only, with server-side sessions.
- **No file attachments.**
- **No real email delivery.** The email handler logs and records `delivered_via: "log"`. In-app notifications are real.
- **Comments are immutable.** No edit or delete. Corrections are new comments, which keeps history append-only.
- **One team per item.** No cross-team transfer or shared ownership.
- **Fixed workflow.** The state machine is defined in code, with no per-team configurable workflows.
- **No @mentions or watchers.** Notification recipients are derived from reporter, assignee and approvers.
- **Org admin UI is minimal.** Team and member management only. No full RBAC editor.
- **Single language, UTC storage.** No i18n.

## Consistency and concurrency

- **Search is near-real-time.** Atlas Search and Vector indexes lag writes by a short time. List views are strongly consistent, search and AI results may briefly miss very recent changes.
- **Only 2xx responses are stored for idempotent replay.** A retry after a failed attempt re-executes against current state. Error responses are not replayed.
- **Idempotency records expire after 24 hours.** A retry after that window is treated as a new request.
- **Live updates are hints, not replayed events.** After a disconnect the client refetches, which is always correct but not incremental.
- **`teams.item_counter` serialises item creation per team.** It is fine for thousands of items per day per team. A ULID-based key would remove the hot spot.

## Scale and operations

- **Atlas free cluster is not a load-test target** (≈100 ops/s, 500 connections). Throughput claims come from the local stack only.
- **SSE fan-out is per API instance** (one change stream per instance). At much larger scale this should move to a dedicated gateway or pub/sub.
- **Outbox polling** adds up to about a second of latency and some read load. It is the first component to replace with a broker at higher volume.
- **`item_events` is unpartitioned.** Growth is handled with indexes today. Sharding by hashed `item_id` or Online Archive is the growth path.
- **Rate limiting is in-process** (per API instance), so limits are approximate across replicas.
- **No automated backups, alerting or dashboards** beyond health endpoints, structured logs and optional metrics.

## AI / RAG

- **English text only**, using a small local embedding model (`bge-small-en-v1.5`). Quality is lower than large hosted models, measured by the evaluation script rather than assumed.
- **Vector retrieval only in v1** (hybrid vector + lexical retrieval with RRF is a stretch item).
- **No reranker and no streaming answers.**
- **Answers depend on an external LLM**, so when it is unavailable or unconfigured the feature degrades to showing the retrieved passages.
- **The LLM can still be wrong.** Mitigations are grounding rules, validated citations and showing sources, but answers should be verified against the cited items.
- **Index freshness:** embeddings are produced asynchronously, so a brand-new comment may not be retrievable for a few seconds.

## Security hardening to do next

- Move audit-log protection into the database (a DB role with insert and find only on `item_events`).
- Add MFA and account lockout policy review, plus password-reset flows.
- Add a CSP report endpoint and dependency scanning gates beyond `pip-audit` / `npm audit`.
- Penetration test the SSE and AI endpoints.

## May change before submission

*(Update this list at the end of the build: anything cut from the P1/P2 tiers in `docs/IMPLEMENTATION_PLAN.md` §5 must appear here. Examples: SSE live updates, hybrid retrieval, Playwright race test, live deployment, load-test report.)*
