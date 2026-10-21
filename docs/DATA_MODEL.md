# Data Model (MongoDB)

Companion to [SYSTEM_DESIGN](SYSTEM_DESIGN.md). Conventions: `_id` is an `ObjectId` unless stated; timestamps are UTC `datetime`; field names are `snake_case`; ids are serialised as strings at the API boundary.

## 1. Modelling principles

1. **Embed what is bounded and read together; reference what grows.** Item state is one document. History, approvals, notifications and chunks grow without bound, so they are separate collections keyed by `item_id`.
2. **One writer path per collection** (repository), so invariants live in one place.
3. **Denormalise for the hot read, derive in code for the rest.** `team_id` is copied onto events and chunks so authorization filters and change-stream fan-out need no joins. `attention_due_at` is stored so "stale" is an index scan.
4. **Append-only history.** `item_events` is only ever inserted into.
5. **Every uniqueness or exclusivity rule is a database constraint**, not an application check (unique and partial-unique indexes).

## 2. Collections

### 2.1 `users`
```json
{ "_id": ObjectId, "email": "priya@acme.io", "name": "Priya Shah",
  "password_hash": "$argon2id$...", "is_org_admin": false, "is_active": true,
  "created_at": ISODate, "last_login_at": ISODate }
```
Indexes: `{email: 1}` **unique** (stored lowercase).

### 2.2 `teams`
```json
{ "_id": ObjectId, "slug": "payments", "name": "Payments Ops", "key_prefix": "PAY",
  "item_counter": 142, "created_at": ISODate }
```
Indexes: `{slug: 1}` unique · `{key_prefix: 1}` unique.
`item_counter` is incremented with `$inc` inside the create-item transaction, so an aborted create leaves no gap. Human key = `PAY-143`.

### 2.3 `memberships`
```json
{ "_id": ObjectId, "team_id": ObjectId, "user_id": ObjectId,
  "role": "viewer|member|lead", "added_by": ObjectId, "created_at": ISODate }
```
Indexes: `{team_id: 1, user_id: 1}` **unique** · `{user_id: 1}` (load "my teams" on every request).

### 2.4 `sessions`
```json
{ "_id": "<sha256 of token>", "user_id": ObjectId, "created_at": ISODate,
  "last_seen_at": ISODate, "expires_at": ISODate, "user_agent": "...", "ip": "..." }
```
Indexes: `{expires_at: 1}` TTL (`expireAfterSeconds: 0`) · `{user_id: 1}` (revoke all).

### 2.5 `work_items`
```json
{
  "_id": ObjectId,
  "key": "PAY-143",
  "team_id": ObjectId,
  "title": "Duplicate charge for order 88213",
  "description": "markdown, max 20k chars",
  "type": "customer_issue|engineering|payment|incident|compliance|task",
  "priority": "P0|P1|P2|P3",
  "status": "open|triaged|in_progress|blocked|pending_approval|resolved|closed",
  "resolution": null,                      // done|wont_do|duplicate|cancelled (set on resolve/close)
  "duplicate_of": null,                    // item _id when resolution = duplicate
  "reporter_id": ObjectId,
  "assignee_id": null,
  "assigned_at": null,
  "requires_approval": true,
  "due_at": null,
  "tags": ["refund", "stripe"],
  "version": 7,                            // optimistic-lock counter, bumped on item field changes
  "content_version": 3,                    // bumped when title/description change (embedding freshness)
  "event_seq": 19,                         // per-item timeline counter, bumped on every event
  "created_at": ISODate,
  "updated_at": ISODate,
  "last_activity_at": ISODate,
  "attention_due_at": ISODate,             // now + SLA(priority, status), recomputed on every event
  "closed_at": null
}
```

**Why two counters.** `version` guards edits (`If-Match`). Comments must not invalidate someone else's edit, so they bump only `event_seq`, which orders the timeline.

**Terminal state** = `closed`. **Active** = every other status.

**Indexes** (ESR: equality, sort, range):

| # | Index | Serves |
|---|---|---|
| 1 | `{key: 1}` unique | Open by human key |
| 2 | `{team_id: 1, status: 1, last_activity_at: -1, _id: -1}` | Team list, status filter, default sort |
| 3 | `{team_id: 1, priority: 1, last_activity_at: -1, _id: -1}` | Priority filter and sort |
| 4 | `{team_id: 1, due_at: 1, _id: 1}` partial `{status ≠ closed, due_at exists}` | Due-date sort, overdue |
| 5 | `{assignee_id: 1, status: 1, last_activity_at: -1}` | "Mine", blocked-mine |
| 6 | `{assignee_id: 1, due_at: 1}` partial `{status ≠ closed, due_at exists}` | Overdue-mine |
| 7 | `{reporter_id: 1, last_activity_at: -1}` | Created-by-me |
| 8 | `{team_id: 1, attention_due_at: 1}` partial `{status ≠ closed}` | **Stale / forgotten work** |
| 9 | `{team_id: 1, priority: 1, assignee_id: 1}` partial `{status ≠ closed, assignee_id: null}` | Unowned-urgent |
| 10 | `{team_id: 1, status: 1}` | Awaiting-approval bucket (`status = pending_approval`) |
| 11 | `{tags: 1, team_id: 1}` | Tag filter (multikey) |

Multi-team queries use `team_id: {$in: [...]}`; MongoDB merges sorted index ranges, so keyset pagination still works.

**Atlas Search index `work_items_search`:**
```json
{
  "mappings": { "dynamic": false, "fields": {
    "title":       [{ "type": "string" },
                    { "type": "autocomplete", "tokenization": "edgeGram", "minGrams": 2, "maxGrams": 15 }],
    "description": { "type": "string" },
    "key":         { "type": "string", "analyzer": "lucene.keyword" },
    "tags":        { "type": "string", "analyzer": "lucene.keyword" },
    "team_id":     { "type": "objectId" },
    "status":      { "type": "token" },
    "priority":    { "type": "token" }
  }}
}
```

### 2.6 `item_events` (append-only audit and timeline)
```json
{
  "_id": ObjectId,
  "item_id": ObjectId,
  "team_id": ObjectId,                     // denormalised for authz filters and SSE fan-out
  "seq": 19,                               // per-item order (from work_items.event_seq)
  "type": "item.created",
  "actor_id": ObjectId,
  "at": ISODate,
  "item_version": 7,                       // item.version after this event
  "request_id": "9f1c2e7a",
  "payload": { }                           // shape depends on type
}
```

| `type` | `payload` |
|---|---|
| `item.created` | `{title, type, priority, team_id}` |
| `item.updated` | `{changes: [{field, from, to}]}` |
| `item.priority_changed` | `{from, to, reason?}` |
| `item.claimed` | `{assignee_id}` |
| `item.released` | `{previous_assignee_id}` |
| `item.assigned` | `{from, to}` |
| `item.status_changed` | `{from, to, reason?, resolution?, duplicate_of?}` |
| `comment.added` | `{body}` (comments are events, so there is no separate collection) |
| `approval.requested` | `{approval_id, note?}` |
| `approval.approved` / `approval.rejected` | `{approval_id, reason?}` |

Indexes: `{item_id: 1, seq: 1}` **unique** (ordering plus a guard against double-writes) · `{item_id: 1, item_version: 1}` (changes since version, for 412 bodies) · `{team_id: 1, _id: -1}` (change-stream fallback polling and team activity).

**Append-only enforcement:** the repository exposes `append()` and reads only. Production hardening: a dedicated DB user with `insert`/`find` on this collection. Atlas free clusters support custom roles, which can take up to ~30 s to apply.

### 2.7 `approvals`
```json
{ "_id": ObjectId, "item_id": ObjectId, "team_id": ObjectId,
  "status": "pending|approved|rejected|cancelled",
  "requested_by": ObjectId, "requested_at": ISODate, "request_note": "...",
  "decided_by": null, "decided_at": null, "decision_reason": null }
```
Indexes: `{item_id: 1}` **unique, partial `{status: "pending"}`** (at most one pending approval per item, enforced by the database) · `{team_id: 1, status: 1, requested_at: -1}` (approver queue).

### 2.8 `outbox`
```json
{
  "_id": ObjectId,
  "type": "notify|index_item|email",
  "payload": { "item_id": "...", "event_id": "..." },
  "dedupe_key": "notify:<event_id>",
  "status": "pending|processing|done|dead",
  "attempts": 0, "max_attempts": 6,
  "next_attempt_at": ISODate,
  "lease_until": null, "locked_by": null,
  "last_error": null,
  "correlation_id": "9f1c2e7a",
  "created_at": ISODate, "completed_at": null,
  "expire_at": null                        // set on done; TTL removes after 7 days
}
```
Indexes: `{status: 1, next_attempt_at: 1}` (poll) · `{dedupe_key: 1}` **unique** · `{lease_until: 1}` partial `{status: "processing"}` (reclaim) · `{expire_at: 1}` TTL.

**Claim operation** (atomic, safe with many workers):
```
find_one_and_update(
  {status: "pending", next_attempt_at: {$lte: now}},
  {$set: {status: "processing", lease_until: now+60s, locked_by: worker_id}, $inc: {attempts: 1}},
  sort=[("next_attempt_at", 1)], return_document=AFTER)
```
A reclaim pass flips `processing` messages with `lease_until < now` back to `pending`.

### 2.9 `notifications`
```json
{ "_id": ObjectId, "user_id": ObjectId, "item_id": ObjectId, "event_id": ObjectId,
  "kind": "assigned|comment|status|approval_requested|approval_decided",
  "title": "...", "read_at": null, "created_at": ISODate,
  "dedupe_key": "<event_id>:<user_id>", "delivered_via": "log" }
```
Indexes: `{dedupe_key: 1}` **unique** (idempotent consumer) · `{user_id: 1, read_at: 1, created_at: -1}` (unread list/count) · `{created_at: 1}` TTL 90 days.

### 2.10 `idempotency_keys`
```json
{ "_id": ObjectId, "user_id": ObjectId, "key": "uuid", "request_hash": "sha256(method+path+body)",
  "response_status": 201, "response_body": { }, "response_headers": { "ETag": "\"1\"" },
  "created_at": ISODate }
```
Indexes: `{user_id: 1, key: 1}` **unique** · `{created_at: 1}` TTL 24 h.

### 2.11 `item_chunks` (RAG)
```json
{
  "_id": "<source_id>:<part>",             // deterministic, so upserts are idempotent
  "item_id": ObjectId, "item_key": "PAY-143", "team_id": ObjectId,
  "kind": "item|comment|decision",
  "source_id": "<item _id or event _id>", "event_seq": 12,
  "text": "...", "text_hash": "sha256", "content_version": 3,
  "embedding": [384 floats], "model": "bge-small-en-v1.5",
  "item_status": "in_progress", "author_id": ObjectId, "created_at": ISODate
}
```
Indexes: `{item_id: 1}` (delete/refresh by item) · `{source_id: 1}`.

**Atlas Vector Search index `chunks_vector`:**
```json
{ "fields": [
  { "type": "vector", "path": "embedding", "numDimensions": 384, "similarity": "cosine" },
  { "type": "filter", "path": "team_id" },
  { "type": "filter", "path": "item_id" },
  { "type": "filter", "path": "kind" }
]}
```
Query shape:
```
{"$vectorSearch": {"index": "chunks_vector", "path": "embedding", "queryVector": qv,
  "numCandidates": 100, "limit": 8,
  "filter": {"team_id": {"$in": user_team_ids}}}}
```
`item_status` is a stored field but intentionally not a filter, because closed items are still valid history for "why did we decide X?".

### 2.12 `ai_queries` (audit and evaluation)
```json
{ "_id": ObjectId, "user_id": ObjectId, "question": "...", "scope": {"item_id": null},
  "retrieved_chunk_ids": ["..."], "cited": ["S1","S3"], "model": "...",
  "latency_ms": {"embed": 22, "retrieve": 61, "generate": 2300}, "degraded": false,
  "created_at": ISODate }
```
Indexes: `{created_at: 1}` TTL 30 days · `{user_id: 1, created_at: -1}`.

## 3. Transactions

All multi-document invariants run inside `UnitOfWork.run(callback)`, which uses `session.with_transaction` (automatic retry on `TransientTransactionError` and unknown commit result). Callbacks must be re-runnable (no external side effects inside).

| Use case | Writes inside one transaction |
|---|---|
| Create item | idempotency record · `teams.item_counter` `$inc` · `work_items` insert · `item_events` (`item.created`) · `outbox` (notify, index) |
| Claim / release / assign | idempotency record · conditional `work_items` update · event · outbox |
| Edit / priority | idempotency or `If-Match` · conditional update (`version`) · event · outbox |
| Transition | conditional update (`version`, `status`) · event · outbox · (approval insert if requested) |
| Comment | idempotency record · `work_items` `$inc event_seq` and activity fields · event · outbox |
| Approval decision | conditional `approvals` update (`status: pending`) · item update · event · outbox |

Keep transactions short: no network calls, no embedding, no large reads.

## 4. Query patterns and their indexes

| Query | Index | Notes |
|---|---|---|
| Item by key | #1 | `find_one` |
| Team list, sorted by activity | #2 | Keyset on `(last_activity_at, _id)` |
| My open work | #5 | |
| Overdue mine | #6 | `due_at < now` |
| Stale (lead) | #8 | `attention_due_at < now` |
| Unowned P0/P1 | #9 | `priority in [P0,P1]`, `assignee_id: null` |
| Timeline | `item_events {item_id, seq}` | Keyset on `seq` |
| Changes since version | `item_events {item_id, item_version}` | For 412 |
| Approver queue | `approvals {team_id, status, requested_at}` | |
| Unread count | `notifications {user_id, read_at, created_at}` | Capped count |
| Text search | Atlas Search `work_items_search` | `team_id` in compound filter |
| Semantic search | Atlas Vector `chunks_vector` | `team_id` pre-filter |

`scripts/explain_queries.py` verifies each of these uses an index scan on the seeded 20k-item dataset.

## 5. Seed data

- `make seed`: 5 users per role archetype, 4 teams (some overlapping memberships), ~300 realistic items with comments and decisions (including deliberate near-duplicates and a few "why did we…" decisions for the demo and golden set).
- `make seed-load`: ~2,000 users, 40 teams, ~20,000 items, ~200,000 events. Embeddings are generated for a configurable subset. Uses bulk inserts.
- Demo accounts and passwords are documented in the README (dev only).
