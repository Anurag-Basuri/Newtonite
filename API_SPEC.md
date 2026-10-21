# API Specification (v1)

Base path: `/api/v1`. This document is the **contract**. The FastAPI implementation must match it, and the generated OpenAPI is used to produce frontend types. If code and this spec disagree, fix one deliberately and update the other in the same commit.

## 1. Conventions

| Topic | Rule |
|---|---|
| Format | JSON, `snake_case`, UTF-8. Timestamps ISO-8601 UTC (`2026-10-22T09:15:00Z`). Ids are strings |
| Auth | Session cookie `opsboard_session` (HttpOnly, SameSite=Lax). All endpoints except `POST /auth/login` and `/healthz` require it |
| CSRF | Unsafe methods require same-origin `Origin`/`Host` and either `Idempotency-Key` or `X-Requested-With: opsboard` |
| Request id | Optional `X-Request-ID` in. Always returned in `X-Request-ID` and in error bodies |
| Idempotency | **Required** on every mutating `POST` except login/logout: `Idempotency-Key: <uuid>`. Missing gives `400`. Replays return the stored response plus `Idempotent-Replay: true` |
| Concurrency | `GET /items/{id}` returns `ETag: "<version>"`. State-changing requests below marked **If-Match: required** need `If-Match: "<version>"`. Missing gives `428`, stale gives `412` |
| Pagination | `?limit=` (default 25, max 100) and `?cursor=`. Response `{ "items": [...], "next_cursor": "..."|null, "has_more": bool }` |
| Item identifier | `{item}` accepts the ObjectId string or the human key (`PAY-143`) |
| Errors | `application/problem+json` (see SYSTEM_DESIGN §10) |
| Visibility | Resources outside the caller's teams return `404` |

### Error body
```json
{ "type": "https://opsboard.dev/errors/version-conflict", "title": "Version conflict",
  "status": 412, "code": "VERSION_CONFLICT", "detail": "...", "request_id": "9f1c2e7a",
  "errors": [], "meta": {} }
```

## 2. Shared schemas

**User (summary)**: `{ id, name, email }`

**Item**
```json
{ "id": "…", "key": "PAY-143", "team": {"id": "…", "name": "Payments Ops", "key_prefix": "PAY"},
  "title": "…", "description": "…", "type": "payment", "priority": "P1",
  "status": "in_progress", "resolution": null, "duplicate_of": null,
  "reporter": {User}, "assignee": {User} | null, "assigned_at": "…" | null,
  "requires_approval": true, "due_at": "…" | null, "tags": ["…"],
  "version": 7, "created_at": "…", "updated_at": "…", "last_activity_at": "…",
  "attention": ["overdue", "stale"],
  "permissions": { "can_edit": true, "can_claim": false, "can_assign": false,
                   "can_comment": true, "allowed_transitions": ["blocked", "pending_approval"] } }
```
`permissions` is computed by the server from the policy so the UI can render controls. It is advisory, and the endpoints re-check every time.

**ItemRow** (list): Item without `description` and `permissions`.

**TimelineEvent**: `{ id, seq, type, actor: {User}, at, item_version, payload }` (payload per DATA_MODEL §2.6, with user ids expanded to names where useful).

**Approval**: `{ id, item_id, status, requested_by, requested_at, request_note, decided_by, decided_at, decision_reason }`

## 3. Endpoints

### 3.1 Auth

| Method | Path | Body | Success | Errors |
|---|---|---|---|---|
| POST | `/auth/login` | `{email, password}` | `200` `{user, teams:[{team, role}]}` and sets cookie | `401 UNAUTHENTICATED`, `429` |
| POST | `/auth/logout` | none | `204`, clears cookie | |
| GET | `/auth/me` | none | `200` `{user, is_org_admin, teams:[{team, role}]}` | `401` |

### 3.2 Teams (read for members, write for org admin)

| Method | Path | Notes |
|---|---|---|
| GET | `/teams` | Teams the caller belongs to, with their role |
| GET | `/teams/{team_id}/members` | Any member of the team. Used by the assignee picker |
| POST | `/teams` | Org admin. `{name, slug, key_prefix}` gives `201` |
| POST | `/teams/{team_id}/members` | Org admin. `{user_id, role}` gives `201` |
| PATCH | `/teams/{team_id}/members/{user_id}` | Org admin. `{role}` |
| DELETE | `/teams/{team_id}/members/{user_id}` | Org admin. `204` |
| GET | `/users?q=` | Org admin. Search users (to add members) |

### 3.3 Items

| Method | Path | Idempotency-Key | If-Match | Success |
|---|---|:-:|:-:|---|
| POST | `/items` | required | | `201` Item, `Location`, `ETag` |
| GET | `/items` | | | `200` list of ItemRow |
| GET | `/items/{item}` | | | `200` Item, `ETag` |
| PATCH | `/items/{item}` | | **required** | `200` Item, new `ETag` |
| POST | `/items/{item}/claim` | required | optional | `200` Item |
| POST | `/items/{item}/release` | required | optional | `200` Item |
| POST | `/items/{item}/assign` | required | **required** | `200` Item |
| POST | `/items/{item}/transitions` | required | **required** | `200` Item |
| POST | `/items/{item}/comments` | required | | `201` TimelineEvent |
| GET | `/items/{item}/timeline` | | | `200` page of TimelineEvent |

**`POST /items`**
```json
{ "team_id": "…", "title": "…", "description": "…", "type": "payment",
  "priority": "P1", "due_at": null, "tags": ["refund"], "requires_approval": null }
```
`requires_approval: null` applies the type default (`payment` and `compliance` default to `true`). Setting it explicitly requires lead. Creates in `open`. Needs member+ in the team. Errors: `403`, `404` (team not visible), `422`.

**`GET /items`** query parameters:

| Param | Values |
|---|---|
| `view` | `mine`, `created_by_me`, `awaiting_my_approval`, `overdue_mine`, `unowned_urgent`, `stale`, `blocked_mine` |
| `team_id` | repeatable, limited to the caller's teams |
| `status`, `priority`, `type` | repeatable |
| `assignee` | `me`, `unassigned`, or a user id |
| `reporter` | user id |
| `due_before` | ISO timestamp |
| `tag` | string |
| `sort` | `-last_activity_at` (default), `priority`, `due_at`, `-created_at` |
| `limit`, `cursor` | pagination |

`view` and explicit filters combine with AND. Invalid cursor gives `400 BAD_CURSOR`.

**`PATCH /items/{item}`** (If-Match required). Any of `title`, `description`, `priority`, `due_at`, `tags`, `type`. Field-level permissions apply (priority: assignee or lead, P0 lead only). Emits `item.updated` and/or `item.priority_changed`. Errors: `403`, `404`, `409 ITEM_CLOSED`, `412`, `422`, `428`.

**`POST /items/{item}/claim`**: sets the assignee to the caller if and only if unassigned. Errors: `409 ALREADY_CLAIMED` (`meta.assignee`), `409 ITEM_CLOSED`, `403` (viewer), `404`.

**`POST /items/{item}/release`**: the caller is the assignee, or lead. Clears the assignee.

**`POST /items/{item}/assign`** `{ "assignee_id": "…" | null }`: lead only. The assignee must be a team member (`422` otherwise).

**`POST /items/{item}/transitions`**
```json
{ "to": "blocked", "reason": "Waiting on bank", "resolution": null, "duplicate_of": null }
```
Validated against the transition table. Errors: `409 INVALID_TRANSITION` (`meta.allowed` lists valid targets), `403 FORBIDDEN`, `422` (missing reason or resolution), `409 ITEM_CLOSED`. The transitions `in_progress → pending_approval`, `pending_approval → resolved` and `pending_approval → in_progress` are **not** accepted here (`409 INVALID_TRANSITION`). Use the approval endpoints.

**`POST /items/{item}/comments`** `{ "body": "…" }` (1–10,000 chars). Member+. Does not change `version`.

**`GET /items/{item}/timeline`**: `?types=` filter, `?cursor=`, `?order=asc|desc` (default `desc`). Keyset on `seq`.

**412 body** (stale write) adds to `meta`: 
```json
{ "current": {Item}, "changes_since": [ {TimelineEvent}, … ], "your_version": 7, "current_version": 9 }
```

### 3.4 Approvals

| Method | Path | Idempotency-Key | If-Match | Notes |
|---|---|:-:|:-:|---|
| POST | `/items/{item}/approvals` | required | **required** | Request approval: `{note?}`. Item must be `in_progress` and `requires_approval`. Moves it to `pending_approval`. `409 APPROVAL_PENDING` if one exists |
| POST | `/approvals/{id}/decision` | required | | `{decision: "approve"|"reject", reason?}`. Lead, **not the requester** (`409 FOUR_EYES_VIOLATION`). Reject needs a reason. Approve moves to `resolved`, reject to `in_progress` |
| POST | `/approvals/{id}/cancel` | required | | Requester withdraws. Item returns to `in_progress` |
| GET | `/approvals?status=pending&team_id=` | | | Approver queue, scoped to teams where the caller is lead |

The decision is a compare-and-set on `approvals.status = "pending"`, so two leads deciding simultaneously yields exactly one winner (the other gets `409 INVALID_TRANSITION`).

### 3.5 Overview

`GET /overview` returns:
```json
{ "generated_at": "…",
  "buckets": [
    { "key": "awaiting_my_approval", "label": "Awaiting your approval", "count": 3, "capped": false, "items": [ItemRow x<=5] },
    { "key": "overdue_mine", … }, { "key": "unowned_urgent", … },
    { "key": "stale", … }, { "key": "blocked_mine", … }, { "key": "mine", … } ],
  "unread_notifications": 4 }
```
`count` is capped at 1000 (`capped: true` renders as "999+").

### 3.6 Search

`GET /search?q=&team_id=&status=&priority=&limit=&cursor=` returns `{ items: [ItemRow + highlights], next_cursor, has_more }`. Backed by Atlas Search. `q` minimum 2 chars. `mode=autocomplete` returns lightweight `{key, title, status}` for the command palette. Falls back to a bounded prefix match when Atlas Search is unavailable (`meta.degraded: true`).

### 3.7 AI

| Method | Path | Body / params | Notes |
|---|---|---|---|
| GET | `/meta/features` | none | `{ ai_enabled, llm_enabled, search_mode }` so the UI can hide features |
| POST | `/ai/similar` | `{title, description?, team_id}` | For the create form. Debounced client-side. Returns `{items:[{key,title,status,assignee,score}]}`. No LLM |
| GET | `/items/{item}/similar` | `?limit=5` | Related items using the item's stored vectors, excluding itself. Scoped to the caller's teams |
| POST | `/ai/ask` | `{question, item_id?, team_id?}` | Rate limited |

**`POST /ai/ask` response**
```json
{ "answer": "Refunds over $500 were routed to approval after the March incident [S1]. …" | null,
  "degraded": false,
  "citations": [ { "marker": "S1", "item_key": "PAY-98", "item_id": "…", "event_seq": 4,
                   "kind": "decision", "snippet": "…", "url": "/items/PAY-98#event-4" } ],
  "retrieved": [ { "marker": "S1", "item_key": "PAY-98", "kind": "decision", "score": 0.83, "text": "…" } ],
  "timings_ms": { "embed": 22, "retrieve": 61, "generate": 2300 } }
```
`degraded: true` means `answer: null` with `retrieved` still populated. Errors: `422` (empty/too long question), `429`, `503 AI_DISABLED`.

### 3.8 Notifications

| Method | Path | Notes |
|---|---|---|
| GET | `/notifications?unread=true` | Cursor-paginated |
| GET | `/notifications/unread-count` | Capped count |
| POST | `/notifications/read` | `{ids: [...]}` or `{all: true}` (Idempotency-Key required) |

### 3.9 Real-time stream

`GET /stream` returns `text/event-stream`. Events:

| `event` | `data` |
|---|---|
| `hello` | `{ "server_time": "…" }` |
| `item.changed` | `{ "item_id", "key", "team_id", "version", "event_seq", "type", "actor_id" }` |
| `notification` | `{ "id", "kind", "item_key" }` |
| `resync` | `{}` (client must invalidate everything) |

A comment line (`: ping`) is sent every 15 s. Hints only. The client refetches via REST.

### 3.10 Admin / ops (org admin)

| Method | Path | Notes |
|---|---|---|
| GET | `/admin/outbox?status=` | Depth, oldest pending age, messages |
| POST | `/admin/outbox/{id}/retry` | Re-queue a `dead` message |
| POST | `/admin/reindex` | Enqueue `index_item` for all items (model change) |

### 3.11 Health

| Path | Notes |
|---|---|
| `GET /healthz` | Liveness, no dependencies |
| `GET /readyz` | Mongo ping, indexes present, Atlas Search/Vector index status, worker heartbeat age |

## 4. Status code summary

`200` OK · `201` created · `204` no content · `400` malformed (`BAD_CURSOR`, `IDEMPOTENCY_KEY_REQUIRED`) · `401` unauthenticated · `403` forbidden · `404` not found or not visible · `409` state conflict · `412` version conflict · `422` validation · `428` precondition required · `429` rate limited · `500` internal · `503` AI unavailable · `504` dependency timeout.

## 5. Worked example: concurrent claim

```
A → POST /api/v1/items/PAY-143/claim   Idempotency-Key: 6f2c…
B → POST /api/v1/items/PAY-143/claim   Idempotency-Key: a91d…

A ← 200 OK  ETag: "8"        { "key": "PAY-143", "assignee": {"name": "Priya Shah"}, "version": 8, … }
B ← 409 Conflict
    { "code": "ALREADY_CLAIMED", "detail": "Claimed by Priya Shah 2 seconds ago.",
      "meta": { "assignee": {"id": "…", "name": "Priya Shah"}, "current_version": 8 } }
```

## 6. Worked example: safe retry

```
POST /api/v1/items  Idempotency-Key: 3b7e…   (timeout, client never sees the response)
POST /api/v1/items  Idempotency-Key: 3b7e…   (retry, same body)
← 201 Created   Idempotent-Replay: true   (same item id, one row, one event)
```
