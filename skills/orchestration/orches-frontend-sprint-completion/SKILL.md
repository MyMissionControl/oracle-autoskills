---
name: orches-frontend-sprint-completion
description: Run an orches orchestrator-worker frontend sprint + its strict completion protocol (build/test, live read-only verify, exact commit, oracle memory, .orches-notes/.orches-done).
installer: auto-skill
created_at: 2026-07-12T15:27:04+00:00
created_session: 
trigger: reusable-workflow
created_by: jack
category: orchestration
content_hash: d0f53621fa1b6999efcfde8af7644531b386e35ca7452e1a928b5b22bd059bd1
---

# Orches frontend sprint — execution + completion protocol

Use when an orches orchestrator (a foreman oracle, e.g. `NN-foreman`) assigns a per-sprint
frontend task in a worktree (`.../projects/<proj>/agents/<role>`), code in a repo
separate from your ψ. Execute the feature, then run the STRICT completion protocol.
Team/project-agnostic — the protocol is the same for any orches team; `<proj>`, `<role>`,
`<app>`, `<server>` and `NN-foreman` are placeholders you fill from the brief.

## Golden rules
- Write ONLY inside the worktree path given. Touch only the stated file zone
  (usually `frontend/` or `client/`); NEVER edit `backend/`/`server/`.
- `node_modules` is often cleared on resume → `npm install` before build/test every time.
- Verify against the REAL backend read-only when it's merged: `npm --prefix <server> start`
  with run_in_background:true, curl the contract, then TaskStop it. NEVER bare `&`.
- A green build ≠ contract-correct. Confirm array-vs-wrapped shapes, response field
  names (e.g. item `starred_by_me` vs star-response `starred`), and 401/400/403/404/502.
- If a spec is ambiguous (e.g. "5 nav links"), pick the sensible reading AND surface it
  in .orches-notes.md — don't silently under/over-deliver.

## Build discipline
- `tsc && vite build` type-checks TEST files too: type your `vi.fn` mocks to the real
  signature (`vi.fn(async (_url: RequestInfo|URL, _init?: RequestInit) => …)`) or
  `.mock.calls` is an empty tuple and the build fails though vitest passes.
- Smoke tests jest-dom-free: `expect(screen.getByLabelText('X')).toBeTruthy()`.
- getByText: exact string = full-textContent equality (leaf); regex = substring (matches
  ancestors → "multiple elements"). Scope with a matcher fn for content in a tag.
- If an anti-power-loss rule is stated: `wip:` commit at subtask boundaries (don't leave
  >1 uncommitted group) + keep a `.orches-progress.md` (usually gitignored).

## Completion protocol — IN ORDER
1. `cd <app> && npm install && npm run build` (clean) AND `npm test` (green). Add the
   test the brief asks for; never delete existing tests.
2. At worktree root: `git add -A && git commit -m "<EXACT message from the brief>"`.
   Confirm only in-zone files staged (no backend/, node_modules, dist).
3. Capture memory to YOUR ψ (auto-hook won't fire cross-repo): `oracle_learn` +
   `oracle_trace` (project=<proj>). Do NOT run `/rrr` — the orchestrator writes the full
   retro once at run-end; a per-sprint worker `/rrr` duplicates the learning (indexer lands
   the repo file centrally too) + costs ~5-6 min. Obey the anti-collision rule: summary
   starts with the orchestrator tag `[NN-foreman]` + `project=<proj>`; shared ψ files append-only.
   - oracle_learn AUTO-SLUGS the summary's first ~45 chars: a long fixed prefix
     (`[NN-foreman] project=<long> …`) collides same-day across sprints (append-only guard
     rejects it). Put the distinguishing token (sprintN) BEFORE the project so the slug is
     unique while still starting with the tag + containing project=.
   - Known infra: `oracle_learn` embedding often fails (`bge-m3 not found`) — the markdown
     still saves; flag it, don't block.
4. Write `.orches-notes.md` at worktree root: FIRST line = plain human language (what the
   user gains, no tech terms), then 2-3 dev-detail lines. If the brief names a verify-gate
   line (e.g. `TEST: cd frontend && npm test`), include it VERBATIM — the merge gate greps it.
5. LAST: create `.orches-done` at worktree root (empty via `touch` unless told otherwise) —
   it signals completion, so nothing after it.

Do not push, do not touch main/other branches.
