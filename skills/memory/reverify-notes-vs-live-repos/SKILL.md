---
name: reverify-notes-vs-live-repos
description: 'Use when a note/memory store''s status claims (UNCOMMITTED, not pushed, DEFERRED, OPEN BUG) must be re-verified against the live repos before reporting what is still open.'
installer: auto-skill
created_at: 2026-08-19T11:38:24+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'memory'
content_hash: 7b6d964d7f481b46bbb7bdcf9ef68886ea21b12089d0d9b64dd01a2c4dd806e4
---
# Re-verify a note/memory store against the live repos

Use when a persistent note store (agent auto-memory, `MEMORY.md` index, a docs/ status
page) has accumulated status claims — "UNCOMMITTED", "not pushed", "DEFERRED",
"OPEN BUG", "waiting on user" — and someone asks what is still true. Notes record the
state at write time; repos move on. Never re-report a stored status without re-deriving it.

## 1. Enumerate only the claims that are checkable
Grep the store for status markers, not for topics:

    grep -lE "UNCOMMITTED|UNPUSHED|NOT pushed|DEFERRED|PARKED|OPEN BUG|STILL OPEN|pending" *.md

Then per file print the marker line with context so you know the exact claim:

    for f in $CANDIDATES; do echo "### $f";
      grep -noE ".{0,80}(UNCOMMITTED|UNPUSHED|NOT pushed).{0,60}" "$f.md" | head -3; done

`grep -o` with a context window beats dumping whole files — a 150-file store dumps
megabytes otherwise.

## 2. Verify by class, cheapest first

**Repo state (one pass, answers most claims at once)**

    for r in $REPOS; do echo "--- $r";
      git -C "$r" status --porcelain | head -5
      git -C "$r" log --oneline @{u}..HEAD | head -5; done

**A named commit** — do not trust "committed, not pushed"; ask the remote:

    git -C "$r" branch -r --contains <sha>

For a fork whose branch tracks an upstream, `@{u}` lies about your own remote. Check
the real one: `git log origin/<branch>..HEAD` — empty means pushed.

**A feature claimed as "not built yet"** — grep the code for the switch/function the
note names, then date it:

    git log -1 --format='%h %ad %s' --date=short -S"<symbol>" -- <file>

This is where stale notes hide: a one-line "waiting on the user" item often shipped
days later in a commit whose subject never mentioned it.

**Cited paths** — files get moved and renamed; a note pointing at `src/status.ts:5`
may now be `src/commands/status.ts:12`. Script it: extract every `` `path.ext` `` from
the store and test existence against each repo root.

**Recent commit bodies are evidence** — `git log --oneline -15 -- <file>` on the
subsystem a bug note names, then `git show -s --format=%b <sha>`. A well-written
commit body will tell you the note is obsolete, and why.

## 3. Trap: file size
`du -h` reports disk blocks, so a 16.7 KB file prints "20K" and looks over a size
budget it never crossed. Use `wc -c` for byte claims.

## 4. Patch the note AND its index
Two edits per stale note:
- the frontmatter `description:` (that is what recall matches — a wrong status there
  poisons every future lookup), and
- a dated line in the body: what is true now, the receipt (sha / path / config value),
  and explicitly that the old sentence was stale.

Do it with a script over a table of (file, description-substitution, status-line);
assert every substitution matched, so a silent no-op cannot pass as done. Keep the
one-line index entry (`MEMORY.md`, README table) in sync in the same pass — an index
that still says UNPUSHED is the line the next session will read.

## 5. Report what changed status, not what you checked
Split the outcome into: closed since the note was written · still open, re-confirmed
today with a receipt · blocked on someone else. A count of files scanned is not a result.
