# Engineering Decisions

Each decision lists the context, the choice, the alternatives rejected, and the trade-off accepted. The system is a modular monolith (FastAPI API plus worker) on MongoDB Atlas with a Next.js frontend. See `docs/SYSTEM_DESIGN.md` for the full design.

---

## 1. MongoDB, with correctness enforced by transactions, conditional updates and unique indexes

**Context.** Work items have a rich, evolving shape, and the history is large and append-only. The brief stresses concurrency and consistency. MongoDB was chosen for the project.

**Decision.**
- One **document per work item** holds current state. Unbounded things (history, approvals, notifications, vector chunks) live in **separate collections** keyed by `item_id`, so documents stay small and the 16 MB limit is never a concern.
- Correctness comes from the database, not from application checks:
  - **Compare-and-set** (`find_one_and_update` with a precondition in the filter) for claims and approval decisions.
  - A **`version` counter** for optimistic locking.
  - **Unique and partial-unique indexes** for invariants (one pending approval per item, unique idempotency key per user, unique notification dedupe key).
  - **Multi-document transactions** only where several writes must commit together (state + event + outbox + idempotency record).
- The **PyMongo Async API** is used, not Motor, which MongoDB has deprecated.

**Alternatives rejected.** PostgreSQL has stronger relational guarantees and I would pick it for a pure ticketing system, but MongoDB was the requirement, and Atlas gives full-text and vector search in the same database. Beanie or another ODM was rejected because hiding the filter inside an ODM makes atomic-update semantics harder to see and explain.

**Trade-off.** Transactions add latency and write-conflict retries, and they are only valid on replica sets. I keep them short and limited to the writes that must be atomic, and document that Atlas free clusters throttle to 100 ops/s, so load testing happens locally.

---

## 2. Three layered defences against concurrent and stale updates

**Context.** Two people claiming the same work, editing an old version, and clicking twice are the situations the brief calls out.

**Decision.**
1. **Claim is atomic.** `find_one_and_update({assignee_id: null, ...})` makes the database pick exactly one winner. The loser gets `409 ALREADY_CLAIMED` naming the winner.
2. **Edits are optimistic.** `ETag`/`If-Match` carry the item `version`. A stale write returns `412` with the current item *and the events since the caller's version*, so the UI can show what changed instead of a generic failure. Comments do not bump `version`, so chatting never blocks anyone's edit.
3. **Retries are idempotent.** `Idempotency-Key` plus a unique `(user_id, key)` index. The key record is written **in the same transaction** as the business write, so there is no window where the action happened but the key was lost.

**Alternatives rejected.** Pessimistic locks or "edit lock" leases (blocks people, needs timeout handling, adds UI complexity). Last-write-wins (silent data loss). Field-level auto-merge on the server (surprising semantics for operational data, so the user decides in the UI).

**Trade-off.** Users occasionally see a conflict dialog. That is intentional: for incidents and payments a visible conflict is better than a silent overwrite. Only successful (2xx) responses are stored for replay, so a retry after a *failed* attempt re-evaluates against current state. That is simpler and avoids replaying stale errors, at the cost of non-idempotent error responses.

---

## 3. Transactional outbox in MongoDB for asynchronous work, not a message broker

**Context.** Notifications and embedding/indexing should not slow the user's request, and must survive crashes, retries and delays.

**Decision.** The business write, the audit event and the outbox messages commit in **one transaction**. A worker polls the `outbox` collection and takes jobs with an atomic `findOneAndUpdate` that sets a **lease**. Failures retry with exponential backoff and jitter, then become `dead` (visible and retryable by admins). Handlers are **idempotent** (unique `dedupe_key` for notifications, deterministic chunk ids and `text_hash` for embeddings), and read *current* state rather than trusting event payloads, so ordering problems are harmless.

**Alternatives rejected.** Redis or BullMQ/Celery (one more system to run, secure and keep consistent with Mongo, and there is still a dual-write problem without an outbox). Fire-and-forget background tasks in the API process (lost on crash).

**Trade-off.** Polling adds up to ~1 s of latency and puts a little read load on Mongo. It is acceptable for notifications and embeddings. It would be the first thing to replace with a broker at much larger scale. The worker is already a separate process, so this swap does not touch the API.

---

## 4. Authorization as one pure policy function, enforced per resource, with 404 for invisible resources

**Context.** Authorization must hold server-side, per resource and per team. Users have different roles in different teams.

**Decision.**
- Team-scoped roles (`viewer < member < lead`) in `memberships`, plus an org-admin flag for administration only.
- All checks go through `policy.can(actor, action, resource)`, a **pure function** with no I/O. The service loads memberships, calls the policy, then writes. This makes the whole permission model testable as a matrix.
- Rules include relationship-aware cases (assignee, reporter) and a **four-eyes rule**: you cannot approve something you requested.
- Resources outside the caller's teams return **404**, not 403, to avoid leaking existence.
- The same enforcement covers search, similar-items, **RAG retrieval** (pre-filter on `team_id` plus a post-retrieval re-check) and SSE fan-out.
- The API also returns a computed `permissions` object so the UI can render controls, which is advisory only.

**Alternatives rejected.** Decorator-only role checks (too coarse for ownership rules). A full ABAC or policy engine such as OPA or Casbin (too heavy for one day, and harder to explain in a review).

**Trade-off.** A custom policy means we own its correctness, so it is the most heavily tested module. Org admins can read all items but cannot act on them without team membership, which adds a step but keeps the audit trail attributable.

---

## 5. A small, hand-built, authorization-aware RAG layer that is optional by design

**Context.** The role is RAG-focused, but the assignment is about backend correctness. AI should add value without risking the core.

**Decision.** Two features: **similar-item / duplicate hints** and **"Ask the history"** (grounded Q&A with citations). Specifics:
- One chunk per semantic unit (item, comment, decision), with a header prefix and splitting only for long text. This beats fixed-size windows for short, structured records.
- Embeddings run **asynchronously** from the outbox; the model is local (`bge-small-en-v1.5` via fastembed) so there is no API key dependency; the provider is an interface.
- Retrieval uses Atlas Vector Search with a **`team_id` pre-filter**, so unauthorized text never reaches a prompt.
- The LLM has no tools. Sources are delimited and treated as **untrusted**. Citations are **validated server-side**. If the LLM is down or unconfigured, the API returns the retrieved passages without an answer (`degraded: true`).
- A **golden-set evaluation script** reports Recall@k, MRR, latency and citation validity.
- The pipeline is hand-rolled (≈200 lines) with clean `EmbeddingProvider` and `LLMProvider` interfaces rather than tied to LangChain or LlamaIndex.

**Alternatives rejected.** Heavy reliance on LangChain or LlamaIndex for this assessment. While these frameworks are industry standards for broad ingestion ecosystems, in this assessment they obscure critical correctness mechanics: tenant/team vector pre-filtering, server-side citation validation, and offline degradation. Our clean provider abstractions (`EmbeddingProvider`, `LLMProvider`) make every retrieval step explicit and testable, while allowing LangChain/LlamaIndex retrievers to be plugged in seamlessly when expanding to multi-source enterprise document ingestion. Fully LLM-driven agent features were also rejected (too unpredictable for core operational ticketing).

**Trade-off.** Hand-rolling means implementing our own chunking, vector filtering, and citation validation routines. For this scope, that is a deliberate strength: every step is visible, testable, and auditable during review. A local embedding model (`bge-small-en-v1.5`) is slightly less expressive than large hosted models, but guarantees zero-cost, local-only testability without external API key dependencies.

---

## Also decided (shorter notes)

- **Comments are events**, not a separate collection. One ordered timeline, one pagination path, append-only by construction. Cost: comment editing is out of scope.
- **Keyset pagination** and **no total counts**. Stable and fast at depth, at the cost of "jump to page N". Overview counts are capped.
- **SSE as invalidation hints**, not data push. One source of truth (REST) and one authorization path, at the cost of a refetch per change.
- **`attention_due_at` stored on the item** so "forgotten work" is an indexed range query with no cron job.
- **Same-origin deployment** (reverse proxy), so first-party cookies, no CORS surface, and straightforward CSRF defence.

## Intentionally not built

SSO/OAuth · file attachments · real email delivery (stubbed) · configurable workflows per team · cross-team transfer · comment editing/deletion · full RBAC admin UI · i18n · mobile app. See `KNOWN_LIMITATIONS.md`.
