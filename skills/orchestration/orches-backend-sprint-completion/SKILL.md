---
name: orches-backend-sprint-completion
description: Run an orches backend sprint (Next.js/Prisma or Express) + its strict completion protocol: build/test/lint, live smoke, exact commit, oracle memory, .orches-notes/.orches-done
installer: auto-skill
created_at: 2026-07-15T12:34:46+00:00
created_session: 
trigger: reusable-workflow
created_by: 09-foreman-2
category: orchestration
content_hash: 25bbb00259977b44a1676af9bef3a433c522b2fe8c18d92de652f3ce3393192f
---
---
name: orches-backend-sprint-completion
description: Run an orches orchestrator-worker backend sprint (Next.js/Prisma or Express/better-sqlite3 style) + its strict completion protocol (build/test/lint, live smoke, exact commit, oracle memory, .orches-notes/.orches-done).
---

# Orches backend sprint — execution + completion protocol

Use when an orches orchestrator (a foreman oracle, e.g. `NN-foreman`) assigns a
per-sprint backend task in a worktree (`.../projects/<proj>/agents/<role>`),
code in a repo separate from your ψ. Execute the feature, then run the STRICT
completion protocol. Team/project-agnostic — `<proj>`, `<role>`, `NN-foreman`
and file paths are placeholders you fill from the brief.

## Golden rules
- Write ONLY inside the given worktree path; `cd` into it first. Touch only
  the stated file zone.
- Treat existing locked contracts (session/auth helper, visibility helper,
  Prisma schema) as read-only inputs — re-read them FRESH for THIS project
  even if a sibling project's sprint brief reads almost identically. Session
  contract SHAPES differ between sibling projects even under a shared task
  template (e.g. one project's session helper reads cookies only via
  `next/headers` with no override parameter, another accepts an optional
  `NextRequest` override) — assuming parity produces tests that can't drive
  the route handlers at all.
- `node_modules` is often wiped on resume → verify key deps exist
  (`ls node_modules/.bin`, check specific package dirs) before assuming
  `npm install` needs a re-run; if a background install's completion
  notification is ambiguous, verify directly rather than blindly re-running it.

## Common backend-specific gotchas (seen repeatedly across sprints)
- **Testing route handlers that call `cookies()`/`headers()` directly**
  (no request-scope available in vitest): mock the module itself —
  `vi.mock('next/headers', () => ({ cookies: async () => jarBackedObject }))`
  — backed by an in-memory `Map`. Production code stays untouched.
- **Vitest missing the project's own `@/*` path alias**: if no prior test
  imported a route/lib file using that alias, `vitest.config.ts` may never
  have needed `resolve.alias` — add it mirroring `tsconfig.json`'s paths the
  first time a test imports through the alias.
- **Storage/disk-write helpers with no injectable root in their given
  contract**: check the same repo for a sibling helper (e.g. a seed script)
  that already solved test/production write isolation, and mirror that
  precedent additively (e.g. an optional env var defaulting to unset =
  unchanged production behavior) rather than inventing a new shape.
- **Stale `next-server`/backend process surviving a session-compaction
  resume**: before diagnosing "broken" reseed/migration behavior, check for a
  stale process bound to the port FIRST (`ps aux | grep next-server`, `ss`/`lsof`
  on the port) — it can serve stale code/DB state and make a working fix look
  broken.
- **Backgrounding a live-smoke server**: before constructing a command that
  redirects logs to a session-scoped tasks directory, confirm that directory
  exists for the CURRENT session (a stale path from a prior session silently
  hangs the command until the shell timeout). Use `nohup ... & disown` with a
  verified log path, never bare `&`.
- Don't leave an unused variable + a workaround comment (e.g. `void x`) to
  dodge a lint error if the variable is genuinely dead — delete it.

## Completion protocol — IN ORDER
1. Implement the feature; `wip:` commit at subtask boundaries (never leave
   more than one uncommitted group). `npm test` green (add required tests,
   never delete existing ones), `npm run build` exit 0, `npm run lint` clean
   on touched files. Do a live HTTP smoke pass against a genuinely fresh
   single-PID server when the brief's acceptance criteria call for it.
2. At worktree root: `git add -A && git commit -m "<EXACT message from the
   brief>"`. Confirm only in-zone files staged.
3. Capture memory to YOUR OWN ψ (cross-repo code means the auto-hook won't
   fire): `oracle_learn` + `oracle_trace` (project=`<proj>`). Do NOT run
   `/rrr` — the orchestrator writes the full retro once at run-end; a per-sprint
   worker `/rrr` duplicates the learning (the indexer lands the repo file in the
   central DB too) and costs ~5-6 min.
   Obey the anti-collision rule: every summary starts with the orchestrator
   tag (e.g. `[NN-foreman]`) + `project=<proj>`; shared ψ files (inbox) are APPEND-ONLY.
   - `oracle_learn` auto-slugs from the summary's leading ~45-58 chars — a
     long fixed mandatory prefix collides same-day across sprints on the same
     project. Front-load a short unique bracketed tag (e.g. `[decision]`,
     `[gotcha]`) immediately after the mandatory prefix, before the
     truncation point, so each call's slug is unique on the first try.
   - Known infra: the embedding step (e.g. `ollama bge-m3`) commonly fails —
     the markdown still saves; flag it as non-blocking, don't retry it.
4. Write `.orches-notes.md` at worktree root: FIRST line = plain
   non-technical language (what the user/product gains), then 1-3 dev-detail
   lines (files/decisions/endpoints touched). Include the brief's exact
   verify-gate line VERBATIM if one is specified (e.g.
   `TEST: cd backend && npm test`) — a merge gate greps for it; if the sprint
   is docs-only, write `TEST: none — <reason>` instead.
5. LAST: create `.orches-done` at worktree root (empty marker, `touch`) —
   nothing after it.

Do not push, do not touch main/other branches.
