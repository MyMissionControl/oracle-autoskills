---
name: repair-misattributed-metadata-column
description: 'Use when a search-filter column was set wrongly by an indexer you cannot edit: re-derive from each row''s own artifact, dry-run the histogram, backup+apply, verify by invariant.'
installer: auto-skill
created_at: 2026-08-07T23:42:48+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude'
category: 'data'
content_hash: 68163e3072446e44e774f7f4987357c3fc75698220350882303b2ee4551b8172
---
# Repair a misattributed metadata column when the producing code is off-limits

Use when an index/DB column that a search filters on (`project`, `owner`, `tag`) was derived
wrongly by an indexer you may NOT edit (vendored, legacy, read-only), so rows exist but are
unfindable. You repair the DATA and accept that new writes keep misfiling.

## 0. Establish the failure mode before touching anything
Read the actual filter SQL. `col = ? OR col IS NULL` (exact) fails **closed**: a query can never
pull the WRONG group, it just cannot see its own. Say which it is — a false-negative bug and a
contamination bug get different urgency and a different fix.

## 1. Derive truth from the artifact, never from the path that broke it
The bad column almost always came from the file's LOCATION. Re-derive from what the artifact
says about ITSELF (frontmatter, an in-text `key=value` convention, a `source:` line). If a row
has no self-statement, **leave it alone** — silence is not permission to guess.

## 2. Dry-run first, and read the target histogram like a bug report
Print `count by new value`. Every junk rule shows up here, not in your tests:
- **first vs last path segment** — `rrr: <owner>/<project>` gave the owner (`fufu-2345`) for 43 rows
- **trailing prose punctuation** — `…-v6.` and `…-v6` split one bucket in two
- **container segments** — reject a stoplist (`projects`, `<org>`, `github.com`) as a name
- **role/worktree tails** — `<repo>/agents/<role>`: if the path has an `agents/` segment, skip the row
- **truncated ids** — a slug cut at N chars yields a half-name. Detect: count==1 AND a strict
  prefix of a busier value → drop, do not extend. Print what you dropped.
Iterate the rules until every bucket is a plausible real name. Two or three rounds is normal.

## 3. Apply
- back up inside the script (`copyFileSync`) — not a separate step someone can skip
- one transaction, `PRAGMA busy_timeout` (live daemons usually hold the DB open; check with `pgrep`)
- `bun:sqlite` gotcha: `{ readonly: false }` throws **SQLITE_MISUSE** — write mode is `{ readwrite: true }`

## 4. Verify with an invariant, not a vibe
Assert the **total row count is unchanged** (proves update-not-delete), then show the before/after
of the bad bucket and the recovered buckets. A repair that silently drops rows looks identical
to a successful one in the log.

## 5. Record that the root cause is still open
The generator is untouched, so the drift returns. Write down: the file:line of the real defect,
that the script must be re-run, and who forbade the upstream fix. Otherwise the next person
reads the clean data and concludes it was fixed.
