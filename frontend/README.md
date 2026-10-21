# Opsboard frontend (template)
Next.js App Router · TypeScript · Tailwind v4 · TanStack Query · react-hook-form · zod.
```bash
npx create-next-app@latest . --ts --tailwind --app --src-dir --no-eslint   # then copy these files over
npm i @tanstack/react-query react-hook-form zod @hookform/resolvers
echo 'BACKEND_URL=http://localhost:8000' > .env.local
npm run dev     # /api/v1/* is proxied to the backend, so cookies stay same-origin
```
Hand-written types live in `src/lib/types.ts`; swap for generated OpenAPI types later (`make openapi`).
Where to expand: `hooks/items.ts` (release, assign, approvals), `items/page.tsx` (more filters), search palette, SSE hook (`/stream` -> `invalidateQueries`).

## Structure (where logic lives)
| Concern | File |
|---|---|
| HTTP contract: Idempotency-Key, If-Match, Problem Details | `lib/api.ts` |
| Error code → plain-language message (one catalogue) | `lib/errors.ts` |
| Status/priority look and labels (one source) | `lib/constants.ts` |
| Query keys, reads, writes, optimistic claim | `hooks/items.ts` |
| SSE hints → refetch | `hooks/live.ts` |
| Error policy per page: 412 → diff panel, else toast | `items/[key]/page.tsx` (`onError`) |
Responsive: side rail ≥ md, top bar + bottom tabs below; 44px touch targets on phones; dark mode via tokens.
