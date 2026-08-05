---
name: nextjs-dev-server-env-vs-vitest-env
description: next dev doesn't inherit vitest.config's inline test.env — create a matching .env.local before smoke-testing with a real dev server
installer: auto-skill
created_at: 2026-07-16T11:00:03+00:00
created_session: 
trigger: error-recovery
created_by: jack
category: nextjs
content_hash: 8796f963bbffc26971997645e1e2b48910778428171391acf9e771f4c5414826
---
## `next dev` doesn't see vitest's inline test env — smoke-test needs its own .env.local

Use when a Next.js project's `vitest.config.ts` sets env vars inline for tests
(e.g. `test: { env: { DATABASE_URL: '...', SESSION_SECRET: '...' } }`) and you
need to manually smoke-test a feature by actually running `npx next dev` and
hitting it with curl/a browser — not just running the test suite.

### The trap

`npx vitest run` passes cleanly (it reads `vitest.config.ts`'s `test.env`
block), which looks like proof the app works. But `npx next dev` in the same
worktree has no knowledge of that config block at all. If there's no committed
`.env`/`.env.local` (common — `.env*` is typically gitignored), any route that
touches the DB or reads an env-gated secret will 500 with something like
"Environment variable not found: DATABASE_URL", even though every test is green.

### Fix

Before smoke-testing via a real dev server, create a local `.env.local`
mirroring whatever `vitest.config.ts`'s `test.env` sets (adjust the DB file
name/path as needed since dev and test usually use separate SQLite files):

```
DATABASE_URL="file:./dev.db"
SESSION_SECRET="dev-only-secret-change-in-production-please-32chars"
```

Next.js auto-loads `.env.local`. Since it's gitignored, this is a one-time
per-worktree setup step — never commit it, don't treat its absence as a bug to
fix in the codebase.

### Why bother with a real dev-server smoke test at all

A route-level vitest test (calling the exported handler function directly)
can pass while still missing integration issues a real HTTP round-trip would
catch — env var wiring being the clearest example, but also things like
cookie propagation across real fetch calls, multipart parsing quirks, or a
page that 500s only under the real Next.js request pipeline. When the task
allows starting a dev server, do a quick real curl-based pass (register a
user, exercise the actual new endpoints, fetch the page) in addition to the
test suite — it's cheap and catches a different class of bug.
