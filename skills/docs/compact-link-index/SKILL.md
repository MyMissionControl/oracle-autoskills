---
name: compact-link-index
description: 'Use when an index-of-files note (memory index, docs TOC, MOC) must shrink to a line or byte budget. Merges by area and gates the draft so no link is orphaned.'
installer: auto-skill
created_at: 2026-08-19T13:16:58+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'docs'
content_hash: f1bc8ed22cf902afdd2e9923c71f5da34b10eca6769c0f12b9b01f71c59b0aa4
---
# Compact a link index without orphaning an entry

Use when a file that is an INDEX of other files (memory index, docs TOC, README of a
folder, MOC/hub note) must shrink to a line/byte budget. The danger is not ugliness —
it is silently dropping a link, which makes the target unreachable from the entry point
while the file still looks complete.

## Rule

Line budgets are met by MERGING lines, not by trimming words. Byte budgets are met by
trimming words, not by merging. Read the budget first and pick the matching lever —
trimming can never reduce a line count.

## Steps

1. Back up to a scratch path (`cp -a index.md $S/index.md.bak-<n>`) so rollback is one `cp`.
2. Read the whole index. Group entries by area (topic, subsystem, decision-type).
3. Build the new draft as a FILE in scratch — never edit the live index in place, so the
   gate runs against something you can still throw away.
4. Merge same-area siblings onto one line, each keeping its own `[title](target)` link
   AND its own verdict/status keyword. Never merge away a status word
   (FIXED/REJECTED/DEFERRED/OPEN/SHIPPED): the status is why the entry earns its place.
5. Run the gate BEFORE installing. Non-empty result = stop and fix the draft:
   ```python
   import re, glob, os
   links = re.findall(r'\]\(([^)]+\.md)\)', open(draft).read())
   files = {os.path.basename(p) for p in glob.glob(DIR + "/*.md")} - {"INDEX.md"}
   missing  = files - set(links)   # a target nobody links = unreachable
   dangling = set(links) - files   # a link to a file that does not exist
   dups     = [l for l in set(links) if links.count(l) > 1]
   ```
   Expect it to catch something: a hand-written merge pass drops ~1 in 150 entries.
6. Install with `cp draft live`, then print the line count and the rollback path.

## Traps

- Do NOT delete an entry because its subject is closed. A closed verdict's value is
  "do not propose this again", which is exactly what a future reader needs.
- If the index's own convention file says "never merge", read WHY. If the reason is
  "merging loses per-item granularity", you may merge lines as long as every per-item
  verdict survives inline — then record the override and the reason.
- State the real downside when you report: merged lines carry less at-a-glance detail,
  so the target files get opened slightly more often.
