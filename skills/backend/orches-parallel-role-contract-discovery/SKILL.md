---
name: orches-parallel-role-contract-discovery
description: Before designing API endpoints for a parallel-role orches sprint, read the sibling frontend role's already-merged code — it's the real contract, not just the brief's prose
installer: auto-skill
created_at: 2026-07-16T14:36:48+00:00
created_session: 
trigger: reusable-workflow
created_by: jack
category: backend
content_hash: e30854a518a125345fd45849c2bddbb6ddd9962ea6ca9b9995b07b7f14a6365c
---
## Discover a parallel role's contract from its already-merged frontend code, not just the brief

Use when an orchestrator (foreman) assigns a backend ("api") role sprint that
runs IN PARALLEL with a sibling frontend role (e.g. "web") on the same sprint
number, and the brief describes endpoints only in prose (route names, rough
field lists). If the parallel role's work has already merged to main by the
time you start, its frontend code is the real contract — more precise, and
more load-bearing, than the brief's prose.

### Steps

1. Pull main first (the brief usually says to). Diff-stat what changed since
   your worktree's prior base (`git diff <old-base>..origin/main --stat`) to
   see if a sibling role's files landed since you last looked.
2. If the sibling's zone is a frontend (`components/**`, `app/(group)/**`),
   read its shared types file first (e.g. a `types.ts` exporting a response
   type) — it's usually the most precise, compact contract statement, more
   reliable to parse than the client component that consumes it.
3. Read the client component(s) that will call your future endpoints — the
   exact fetch call (method, URL, query param names, body shape/field names,
   Content-Type) is the literal request/response contract to match. It often
   diverges from the brief's prose in small but breaking ways (e.g. the brief
   says field `repoUrl`, the actual frontend code sends `githubUrl`; the
   brief says `?tag=<name>`, the actual code sends `?tag=<numeric id>`).
4. If the frontend has a graceful-degradation/mock fallback (falls back to
   mock data when the fetch fails), its `MOCK_*`/fallback constant usually
   restates the assumed contract explicitly — treat it as corroborating
   evidence, not just the live fetch call.
5. Only fall back to the brief's prose for whatever the frontend doesn't
   consume yet (admin-only endpoints, pages still stubbed "coming in a later
   sprint") — there you have real freedom to pick your own response shape,
   and should document that choice for whichever role builds against it next.

### Why this matters

Catching a contract mismatch after merging (e.g. via a pre-merge review that
finds a missing field) costs a whole review-fix-recommit cycle. Catching it
during your own reconnaissance, before writing any route code, costs nothing
extra — you were about to open the schema/auth files anyway, and the
sibling's frontend files are just a few more reads in the same pass.
