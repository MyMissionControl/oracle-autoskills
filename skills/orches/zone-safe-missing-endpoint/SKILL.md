---
name: zone-safe-missing-endpoint
description: In an orches parallel-role sprint, resolve UI data from an endpoint owned by a sibling/future role via server-side Prisma in your own page.tsx instead of creating an out-of-zone API route
installer: auto-skill
created_at: 2026-08-02T02:30:29+07:00
created_session: 
trigger: reusable-workflow
created_by: mike-oracle
category: orches
content_hash: 3c200b5e798eca1100f76f4f7f0d5c28f5a8fbac093080a1cc100bc61ccced0b
---
## When this applies

You're building a frontend role in an orches parallel-role sprint (zones like
`app/<feature>/**`, `components/<feature>/**`). Your UI needs data that would
normally come from an API endpoint (e.g. "groups the current user belongs to",
"current session identity"), but that endpoint:

- belongs to a sibling role's zone (`app/api/<feature>/[id]/**`, `lib/<feature>/**`)
  that hasn't merged into your worktree yet, or
- is explicitly planned for a LATER sprint's zone (check `docs/plan.md` — a future
  role like `admin-api` may own it, e.g. `app/api/groups/**`).

Writing that endpoint yourself would step outside your declared zone and collide
with the role that's supposed to own it later.

## Fix

Next.js (App Router) Server Components run server-side. Resolve the missing data
directly via the already-merged data layer inside your OWN zone's `page.tsx`, and
pass the result down as a prop into your client component — don't invent a new API
route outside your zone.

This also sidesteps the httpOnly-cookie problem: client JS can't read session
identity directly, so if any owner/admin-only UI gating is needed, resolve the
session server-side too and pass `currentUserId`/`currentRole` down as plain props.
The client component then never needs an async auth-loading step of its own — no
race to guard against.

## Steps

1. Confirm the endpoint truly doesn't exist yet: check the sibling role's
   worktree/branch for a diff against main, and check `docs/plan.md` for which
   future sprint's zone is supposed to own it.
2. In your zone's Server Component (`app/<feature>/[id]/page.tsx`), import the
   shared server-side helpers already used elsewhere in the repo (e.g. the
   Prisma client, `getSession()`) — these are read-only imports of already-merged
   code, not writes into another role's zone.
3. Query directly for exactly what the client needs (minimal projection, e.g.
   just `{id, name}`), and pass it as a typed prop into the client component.
4. Pass current identity (`userId`, `role`) as props too if the UI needs an
   owner/admin gate — never derive it from a client-side fetch to an endpoint
   that doesn't exist yet.
5. Document the interpretation in the sprint's notes/acceptance checklist: which
   endpoint doesn't exist yet, why you resolved it this way instead, and that a
   future sprint replacing it with a real endpoint is expected (so the next
   worker isn't surprised to find server-side DB access in a page that "should"
   just be calling an API).
