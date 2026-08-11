---
name: enable-tenant-labelling-with-blind-writer
description: 'Use when switching a shared single-store app to per-owner scoping and the live writer ignores the scope column — stamp after write, ship OFF, prove zero behaviour change.'
installer: auto-skill
created_at: 2026-08-11T14:07:24+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'data-migration'
content_hash: 080258dee7f0785216fd75ed51dcbb472104e7e79567f30eee29cddcf817f2da
---
---
name: enable-tenant-labelling-with-blind-writer
description: Use when switching a shared single-store app (one SQLite/DB for many owners) to per-owner scoping and the live writer ignores the scope column — stamp after write, ship the switch OFF, prove zero behaviour change.
---

# Per-owner scoping when the live writer is scope-blind

The classic trap: the schema has `<scope>_id` (tenant/org/owner) with a DEFAULT, the read
path filters on it, and everyone assumes "set the env var and it isolates". Then rows keep
landing in the default scope because **the process that actually writes doesn't know the
column exists** (a pinned fork, an older vendored copy, a separate indexer/worker).

## 1. Find the real writer before designing anything

Do not trust the main repo's code as the write path.

```bash
# who spawns the writer, and from where?
rg -n "spawn|exec|systemd|cron" <launcher-or-watcher-file>
# does that code even mention the scope?
rg -c "<scope>" <writer-root>/src        # 0 hits = scope-blind writer
rg -n "<scope>" <writer-root>/src/db/schema.*   # no column = INSERT omits it = DEFAULT applies
```

Also separate *declared* constraints from *enforced* ones:

```bash
# FK "references()" in an ORM means nothing if the pragma is off
sqlite: PRAGMA foreign_keys;   # 0 = not enforced, rows with unknown scope insert fine
```

And distinguish the two resolver helpers most of these codebases have:
`currentScope()` returns undefined → **no filter → sees everything**;
`activeScope()` falls back to the default → **hard-filters the default**.
Only the second set of call sites breaks when you relabel rows. Enumerate them:

```bash
rg -n "activeScope\(\)|DEFAULT_SCOPE" src --type ts | grep -v test
```

## 2. Stamp after write instead of teaching the blind writer

You usually cannot patch the writer (pinned fork, read-only vendored code, upstream
divergence = its own downside). Put the labelling in the wrapper *you* own, right after a
successful write, keyed off each row's own provenance column (`source_file`, `path`, `origin`):

```ts
run(writer).then(() => stamp().catch(e => console.error('stamp skipped:', e)))
           .then(() => process.exit(0))
```

Rules that make this safe:
- **Fail OPEN.** On any stamping error leave rows in the default scope — visible to everyone.
  Failing closed produces written-but-unfindable data, the worst outcome.
- **Never guess provenance.** Exact prefix match, then exact secondary-column match, then
  leave the row alone. Report the unattributable count out loud (there is always a tail of
  rows whose path was recorded relative to some other root).
- Resolve config most-specific-first: absolute path → canonical scope string → bare name.

## 3. Ship the switch OFF and prove it is off

Config file ships empty (`{"<owners>":{}}`); missing / malformed / empty all mean
"nothing mapped". Add an env override (`<APP>_SCOPE_MAP=...`) purely so tests can point at
a temp config.

## 4. Migration: dry-run default, journal, exact revert

One CLI, four modes: `--report` (default, read-only) · `--audit` (what *could* be
attributed, ignoring the map) · `--apply` · `--revert <journal>`.

- Backup with `VACUUM INTO 'file'` — consistent even with WAL active, unlike `cp`.
- Journal every prior value as JSONL **before** the UPDATE, then update in one transaction.
- Revert applies the journal row-by-row (`SET scope=prev WHERE id=? AND scope=next`), so it
  is exact and safe to re-run.

## 5. Verification that actually earns "no downside"

Always against a **copy**: `VACUUM INTO` a scratch dir and point the app's data-dir env at it.

1. Empty config + run the **real** wrapper → exit 0, histogram unchanged, no config-created
   rows, no log line. This is the zero-behaviour-change proof; a unit test does not give it.
2. Mapped config → rows stamped, and assert **every** stamped row is owned by that owner
   (re-derive ownership from its own provenance column, don't trust the count).
3. Other owners' rows untouched; counts still sum to the total.
4. `--apply` → `--revert` → diff `id → scope` against the pre-apply snapshot: **0 per-row
   diffs**, not just a matching histogram.
5. Re-`--apply` → 0 changes (idempotent).

## Gotchas

- `bun:sqlite`: `new Database(f, { readonly: false })` throws `SQLITE_MISUSE`. Pass
  `{readonly:true}` or **no options at all**.
- `bun -e '...' -- arg` does not put `arg` at `process.argv[2]`; pass values via env.
- Owner keys that are bare directory names collide when two roots share a basename — support
  the fully-qualified key too, most-specific wins.
- Labelling is only half of scoping. Writers must label AND readers must declare the scope;
  do one without the other and you get write-here / search-there silent misses.
