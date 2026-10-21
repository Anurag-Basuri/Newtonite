# AGENTS.md: Rules for AI coding agents

Read this file first, then the doc sections your task references. If anything here conflicts with a request, **stop and ask**.

## Source of truth

| Topic | Document |
|---|---|
| Architecture, behaviours, patterns, errors | `docs/SYSTEM_DESIGN.md` |
| Collections, fields, indexes | `docs/DATA_MODEL.md` |
| Endpoints, headers, error codes | `docs/API_SPEC.md` (this is the contract) |
| What to test | `docs/TEST_PLAN.md` |
| Order of work | `docs/IMPLEMENTATION_PLAN.md` |

Do not invent endpoints, fields, error codes or collections. If something is missing, propose a change to the doc in the same PR and flag it.

## Stack (fixed)

Backend: Python 3.12, FastAPI, Pydantic v2, **PyMongo Async API (`AsyncMongoClient`)**. Do **not** use Motor. Do **not** use Beanie or another ODM. Database: MongoDB (Atlas, or `mongodb-atlas-local`). Frontend: Next.js App Router, TypeScript, Tailwind, TanStack Query, shadcn/ui, react-hook-form, zod. No LangChain or LlamaIndex. No Redis, no message broker.

## Architecture rules (violations are bugs)

1. **Layering:** router → service → (domain, repository). Routers contain no business logic. Only repositories touch collections. `domain/` performs no I/O.
2. **Authorization:** every service method calls `policy.can(...)` before writing. Never check roles inline elsewhere. Resources outside the caller's teams return **404**.
3. **Atomicity:** any use case that writes more than one document runs inside `UnitOfWork.run(...)` (`with_transaction`). Callbacks must be safe to re-run: no network calls, no randomness that changes outcomes, no external side effects inside.
4. **State, event and outbox together:** every mutation appends exactly one `item_events` document and enqueues its outbox messages **in the same transaction** as the state change.
5. **Concurrency primitives, not checks:** use conditional updates (`find_one_and_update` with the precondition in the filter) for claim and approval decisions, and `version` filters for edits. Never read-then-write for these.
6. **Idempotency:** every mutating `POST` (except login/logout) goes through `infra/idempotency.py`, with the record written inside the business transaction. `PATCH`/commands marked in API_SPEC require `If-Match`.
7. **Query safety:** build Mongo filters from typed parameters. Never pass a request dict (or `**kwargs` from a request) into a filter or update. Reject `$`-prefixed keys in free-form input.
8. **Bounded reads:** every list endpoint is keyset-paginated with a max limit of 100, uses a documented index, and uses projections. No `skip`, no unbounded `to_list()`, no loading collections into memory. If you need a new query, add the index to `DATA_MODEL.md` and `db/indexes.py`.
9. **History is append-only:** `item_events` has no update or delete code path.
10. **Async handlers are idempotent** and read current state, not event payloads. Use deterministic ids and dedupe keys.
11. **AI is optional:** all AI code sits behind `EmbeddingProvider`/`LLMProvider` and feature flags. The core app must work with `AI_ENABLED=false`. Retrieval always applies the `team_id` pre-filter **and** a post-retrieval policy re-check. LLM output is untrusted. Validate citations. The LLM gets no tools.
12. **Errors:** raise `DomainError` subclasses with a catalogued `code`. All responses use Problem Details. No stack traces or internals in responses.
13. **No hidden globals:** inject the clock, providers and DB through FastAPI `Depends` so tests can override them.
14. **Frontend:** server state in TanStack Query only. Filters live in the URL. Generate types from OpenAPI. Reuse one `Idempotency-Key` per user intent across automatic retries. Never trust the UI to enforce permissions.

## Testing rules

- Write the P0 tests in `docs/TEST_PLAN.md` **before** implementing the behaviour.
- Concurrency, transactions, idempotency, outbox and pagination are tested against **real MongoDB** (`atlas-local`), never mocks.
- Name tests with the plan id, for example `test_T_CLM_1_concurrent_claim_single_winner`.
- A task is not done until its tests pass and `make check` is green.

## Code style

- Python: `ruff` (lint and format), `mypy` strict on `app/domain` and `app/infra`, full type hints, `async def` for I/O, small functions, docstrings that state *invariants*, not narration.
- TypeScript: strict mode, no `any`, ESLint clean, components small and typed.
- Comments explain *why* (especially around concurrency). No dead code or commented-out code.
- Conventional commits (`feat:`, `fix:`, `test:`, `docs:`, `refactor:`), small and reviewable. Never commit secrets or `.env`.

## Files that require human review (do not "improve" casually)

`backend/app/db/uow.py` · `backend/app/infra/idempotency.py` · `backend/app/infra/outbox.py` · `backend/app/domain/policy.py` · `backend/app/domain/workflow.py` · conditional-update repository methods. If you change one, say so prominently in the commit message and add or adjust a test.

## Do not

- Add features that are not in the docs (SSO, attachments, comment editing, real email, workflow editors).
- Replace a P0 behaviour with a simpler non-atomic version "for now".
- Catch and swallow exceptions around database writes.
- Use `time.sleep` in tests (use `wait_until` with a timeout).
- Hard-code model names, URLs, secrets or team ids.
- Rewrite large files or reformat unrelated code in a feature commit.

## Commands

`make up` · `make up-local` · `make seed` · `make indexes` · `make test` · `make lint` · `make typecheck` · `make eval` · `make explain` · `make openapi` · `make check`
