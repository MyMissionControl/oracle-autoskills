---
name: fix-vitest-sqlite-busy-without-shared-config
description: 'Fix intermittent P1008/SQLITE_BUSY in a shared-test.db vitest suite via --no-file-parallelism on the invocation, not by touching adapter timeout/WAL or a zone-locked shared vitest config'
installer: auto-skill
created_at: 2026-08-30T12:29:15+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'bob'
category: 'testing'
content_hash: 41e98ca4d210356de275cae9bbe708b07f89d25647998f80540ce91b3a49f986
---
---
name: fix-vitest-sqlite-busy-without-shared-config
description: Fix intermittent P1008/SQLITE_BUSY timeouts in a Prisma+libsql/better-sqlite3 vitest suite that shares one test.db across many parallel test files, without editing shared/zone-locked config
---

# Symptom

`vitest run` against a Prisma (libsql or better-sqlite3 adapter) suite that all points at one
shared `test.db` starts throwing intermittent `P1008 SocketTimeout` / `SQLITE_BUSY` errors on
plain `upsert`/`create` calls — usually right after the test suite grows past a handful of files
(e.g. a new sprint/role adds several new `*.test.ts` files on top of an existing suite that was
previously green). Rerunning shows **different tests fail each time** — that's the signature of
write-write contention across vitest's parallel test-file workers, not a logic bug.

# Do NOT

- Don't touch the Prisma/libsql adapter's `timeout:` value or remove `PRAGMA journal_mode=WAL` —
  those exist specifically to reduce (not eliminate) this class of failure, and removing either
  makes it worse, not better.
- Don't edit the shared `vitest.config.mts`/`vitest.global-setup.mts` if you're one of several
  parallel roles/workers with a locked zone — that file is outside any single zone and a config
  edit there silently changes test behavior for every other role's suite too.

# Fix

1. Confirm it's contention, not a real bug: rerun the full suite 2-3 times. If the *set* of
   failing tests changes between runs, it's contention.
2. Confirm the fix before proposing it: run once with the CLI flag that serializes test files
   (Vitest: `--no-file-parallelism`; check `npx vitest --help | grep -i parallel` for the exact
   flag on the installed version). Run it 2-3 times — it should be green every time once files no
   longer race each other for the same sqlite file.
3. Apply the fix at the invocation layer, not the config layer: put the flag directly in whatever
   command your task's completion protocol asks you to report as the verify/test command (e.g. a
   `TEST:` line consumed by a merge gate), instead of editing the shared config file. This keeps
   the fix scoped to your own suite's invocation and leaves every other parallel worker's config
   untouched.
4. Note the tradeoff in your handoff notes: serializing file execution trades some wall-clock time
   for reliability — call this out so a later sprint that keeps adding test files doesn't have to
   rediscover the same root cause from scratch.
