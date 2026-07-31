---
name: resume-orchestrated-worktree-safely
description: Safely resume a worktree/branch that an orchestrator merged/stashed between your sessions: grep for committed conflict markers, restore gitignored local state, FK-order test cleanup
installer: auto-skill
created_at: 2026-07-31T09:22:25+07:00
created_session: 
trigger: error-recovery
created_by: bob
category: workflow
content_hash: 036a0aae732a256b89d48f9e8763fa8e7c2eddde28a6011a345d26b00e33dbfd
---
## When to use

Resuming work in a git worktree/branch that an orchestrator (or any other automated process) previously merged, stashed, or fast-forward-pulled between your sessions — common in multi-agent/multi-sprint build pipelines where a worker picks up a worktree it didn't leave in the same state it left.

## Procedure

1. **Don't trust a clean `git status` alone.** A prior stash-pop or merge gone wrong can leave literal `<<<<<<< / ======= / >>>>>>>` conflict markers committed as real file content — `git status`/`git diff` show nothing unusual because there's no live conflict, just bad content already committed. Before editing any file you're about to extend (especially config files like `.gitignore`, `package.json`, CI configs), grep it for conflict markers: `grep -n "<<<<<<<\|=======\|>>>>>>>" <file> || echo "none found"`. If found and the file is in your allowed edit zone, resolve by merging both sides' intent (often a simple union, not a real semantic conflict) and commit that fix as its own `wip:` commit before starting your actual task.

2. **Expect gitignored local state to be gone.** `node_modules/`, `.env`, generated build/client output (e.g. a Prisma generated-client folder), and any other locally-generated-but-gitignored files won't survive a fresh clone or a merge-through-GitHub cycle. At the start of a resumed sprint: reinstall dependencies (`npm install`), recreate any `.env` from `.env.example` (or your own knowledge of the expected values), and rerun any codegen step (e.g. `prisma generate`) before writing new code — don't assume last session's local setup is still there.

3. **Order test cleanup by foreign-key dependency, not convenience.** When a test's `afterAll` deletes seeded rows (e.g. test users) that other rows reference (e.g. their created records, join-table rows), a naive `deleteMany` on the parent throws a FK constraint error — and most test runners count a throwing `afterAll` as a failed test file even when every assertion inside passed. If the schema has no cascade-delete configured, delete children before parents in dependency order (e.g. join/junction tables → owned records → membership tables → the root entity), or just don't bother deleting rows from an isolated per-run test database that gets wiped by global setup anyway (only clean up what could pollute a *shared* database or *other test files in the same run*).

## Why this matters

In multi-agent/orchestrated pipelines, the assumption "the worktree is exactly as I left it" is unsafe — other automated actors (an orchestrator's git operations, a merge step, a stash from a different flow) can leave artifacts that look like normal files but are actually broken merges, and gitignored setup state simply doesn't travel through git at all. A five-second grep and a routine reinstall at the top of a resumed sprint is far cheaper than debugging a mysterious build failure that traces back to committed conflict markers or a missing `.env`.
