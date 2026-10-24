# Engineering Decisions

A concise breakdown of the 5 core architectural decisions for Opsboard.

---

### Quick Decision Matrix

| # | Decision | Core Mechanism | Key Trade-Off | Primary Implementation Files |
|---|---|---|---|---|
| **1** | **MongoDB + PyMongo Async API** | ACID transactions (`with_transaction`) + atomic CAS updates. No ODM or Motor. | Latency overhead for replica set transactions; kept brief. | [`db/uow.py`](file:///d:/projects/Newtonite/backend/app/db/uow.py)<br>[`db/client.py`](file:///d:/projects/Newtonite/backend/app/db/client.py)<br>[`db/indexes.py`](file:///d:/projects/Newtonite/backend/app/db/indexes.py) |
| **2** | **Three-Layer Concurrency Defences** | 1. **Claims:** Atomic CAS (`assignee_id: null`) → 409 on race.<br>2. **Edits:** `If-Match: "<version>"` → 412 on stale write.<br>3. **Retries:** `Idempotency-Key` committed in same txn. | Users occasionally see conflict dialogs rather than silent data overwrites. | [`repositories/items.py`](file:///d:/projects/Newtonite/backend/app/repositories/items.py)<br>[`infra/idempotency.py`](file:///d:/projects/Newtonite/backend/app/infra/idempotency.py)<br>[`api/items.py`](file:///d:/projects/Newtonite/backend/app/api/items.py) |
| **3** | **Transactional Outbox (No Message Broker)** | Mutations, audit events, and outbox jobs commit in **one transaction**. Worker polls with 30s atomic leases and exponential backoff. | Polling adds ~1s latency. Zero dual-write risk; no external Redis/RabbitMQ. | [`infra/outbox.py`](file:///d:/projects/Newtonite/backend/app/infra/outbox.py)<br>[`worker.py`](file:///d:/projects/Newtonite/backend/app/worker.py)<br>[`repositories/notifications.py`](file:///d:/projects/Newtonite/backend/app/repositories/notifications.py) |
| **4** | **Pure Authorization Policy + 404 Obscurity** | `policy.can(actor, action, resource)` is a pure function (zero I/O). Enforces **Four-Eyes** (requester cannot self-approve). Foreign items return **404** (not 403). | Custom policy requires matrix testing (43 test cases in test suite). | [`domain/policy.py`](file:///d:/projects/Newtonite/backend/app/domain/policy.py)<br>[`domain/workflow.py`](file:///d:/projects/Newtonite/backend/app/domain/workflow.py)<br>[`services/approval_service.py`](file:///d:/projects/Newtonite/backend/app/services/approval_service.py) |
| **5** | **Grounded RAG with Team Pre-Filtering** | Semantic chunking, MongoDB `$vectorSearch` pre-filtered by caller's `team_id`s, Groq LLM synthesis, server-side citation validation, circuit breaker. | Hand-rolled pipeline (≈200 lines) instead of LangChain; fully testable and isolated. | [`services/ai_service.py`](file:///d:/projects/Newtonite/backend/app/services/ai_service.py)<br>[`infra/ai/providers.py`](file:///d:/projects/Newtonite/backend/app/infra/ai/providers.py)<br>[`repositories/chunks.py`](file:///d:/projects/Newtonite/backend/app/repositories/chunks.py) |

---

### Detailed Summary

#### 1. Database & Atomicity (MongoDB via PyMongo Async)
- **Why:** Work item shapes evolve; history is append-only. Native `AsyncMongoClient` provides direct control over query plans and transactions without Motor or ODM abstractions.
- **Rules:** State in `work_items`; unbounded data (`item_events`, `approvals`, `outbox`) stored in separate collections to avoid MongoDB's 16 MB limit.
- **Files:** [`uow.py`](file:///d:/projects/Newtonite/backend/app/db/uow.py) · [`client.py`](file:///d:/projects/Newtonite/backend/app/db/client.py) · [`indexes.py`](file:///d:/projects/Newtonite/backend/app/db/indexes.py)

#### 2. Concurrency & Stale Updates
- **Why:** Prevent race conditions in high-concurrency environments.
- **Rules:**
  - **Claim Race:** Atomic `find_one_and_update({"_id": id, "assignee_id": None})`. Single winner; loser gets HTTP 409.
  - **Stale Edits:** `If-Match: "<version>"` checks version on save; stale writes return HTTP 412 with timeline diff. Comments do not bump `version`.
  - **Idempotency:** Unique `Idempotency-Key` stored inside the business transaction.
- **Files:** [`repositories/items.py`](file:///d:/projects/Newtonite/backend/app/repositories/items.py) · [`infra/idempotency.py`](file:///d:/projects/Newtonite/backend/app/infra/idempotency.py) · [`api/items.py`](file:///d:/projects/Newtonite/backend/app/api/items.py)

#### 3. Transactional Outbox Pattern
- **Why:** Eliminates the dual-write hazard between database mutations and notifications/indexing.
- **Rules:** State change, event, and outbox job commit in the **same transaction**. Background worker claims jobs with atomic 30s leases and dedupe keys.
- **Files:** [`infra/outbox.py`](file:///d:/projects/Newtonite/backend/app/infra/outbox.py) · [`worker.py`](file:///d:/projects/Newtonite/backend/app/worker.py) · [`notifications.py`](file:///d:/projects/Newtonite/backend/app/repositories/notifications.py)

#### 4. Authorization & Security (Four-Eyes + 404s)
- **Why:** Centralized, auditable access control that prevents unauthorized resource enumeration.
- **Rules:** Pure function `can(actor, action, resource)`. Requesters are blocked from approving their own items. Requests for unauthorized teams return HTTP 404 (not 403).
- **Files:** [`domain/policy.py`](file:///d:/projects/Newtonite/backend/app/domain/policy.py) · [`domain/workflow.py`](file:///d:/projects/Newtonite/backend/app/domain/workflow.py) · [`approval_service.py`](file:///d:/projects/Newtonite/backend/app/services/approval_service.py)

#### 5. Grounded AI & Multi-Tenant Retrieval (Groq Cloud)
- **Why:** Fast history Q&A and duplicate prevention with zero cross-tenant data leakage.
- **Rules:** Hard query-time pre-filter on `team_id` in `$vectorSearch`. Post-retrieval read policy re-check. Sever-side citation verification strips hallucinated markers. Circuit breaker falls back to raw passages if LLM is offline.
- **Files:** [`ai_service.py`](file:///d:/projects/Newtonite/backend/app/services/ai_service.py) · [`providers.py`](file:///d:/projects/Newtonite/backend/app/infra/ai/providers.py) · [`repositories/chunks.py`](file:///d:/projects/Newtonite/backend/app/repositories/chunks.py)

---

### Related Documentation Links
- Full Architecture & Sequence Diagrams: [`docs/SYSTEM_DESIGN.md`](file:///d:/projects/Newtonite/docs/SYSTEM_DESIGN.md)
- HTTP REST Contracts & Error Codes: [`docs/API_SPEC.md`](file:///d:/projects/Newtonite/docs/API_SPEC.md)
- Interview Demo Script & Top 20 Q&As: [`docs/INTERVIEW_GUIDE.md`](file:///d:/projects/Newtonite/docs/INTERVIEW_GUIDE.md)
