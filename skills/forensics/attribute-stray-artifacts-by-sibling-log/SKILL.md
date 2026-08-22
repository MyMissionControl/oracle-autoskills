---
name: attribute-stray-artifacts-by-sibling-log
description: 'Use when a tool wrote files to the wrong place and you must prove which call site did it: correlate residue presence with the co-written log that records its own input path, across every instance on…'
installer: auto-skill
created_at: 2026-08-21T08:02:32+07:00
created_session: 
trigger: 'complex-task'
created_by: 'subagent-verifier'
category: 'forensics'
content_hash: 342be3940beb044c4c6590997652d9f31a9de4ba2b187089f67e40c1c8e7255d
---
# Attribute stray artifacts by sibling-log correlation

Use when a tool left files in the WRONG place (unnamespaced siblings of the
correct per-run dirs, duplicates, orphans) and you must prove WHICH call site
wrote them — without trusting a top-down code read.

## Why not read the code first
A function like `write_stuff <ROOT>` derives every output path from its one
argument. Reading it tells you the *shape* of the output, never *who* passed the
bad argument. Attribution comes from the artifacts.

## Procedure

1. **Enumerate every instance, not just the reported one.**
   `for d in <parent>/*/; do ls -1a "$d/<artifact-dir>"; done`
   Plain `find` hides dot-dirs under some shell hooks — use `ls -a`,
   Glob, or the raw-proxy form of find.
   Split into HAS-residue vs CLEAN. A claim proven on n=1 is a coincidence.

2. **Find the co-written sibling that records its own input.**
   The function that wrote the stray files almost always also writes a log /
   manifest / receipt next to them, and that file usually prints the path it was
   given (`=== run @ <ts> · target=<PATH> ===`). That single line is the
   attribution: `target=<root>` vs `target=<root>/workers/<x>` names the caller.
   `sed -n '1p'` and `sed -n '/<outputs-line>/p'` — a grep-rewriting hook
   truncates long lines, sed does not.

3. **Test the correlation across ALL instances.**
   residue-present ⟺ sibling-log-present, with no exception, is proof.
   Any instance with the log but no residue (or vice versa) means a second
   mechanism exists — go find it before reporting.

4. **Timestamp-order the write.**
   `ls -la --time-style=full-iso` for sub-second stamps. Compare stray-file
   mtimes against (a) the log header timestamp, (b) the correct archive copy's
   mtime. Order proves "written before the archive step" vs "leftover of it".
   **Directory mtime is the last entry ADD/REMOVE, not the last write** — a dir
   older than the files inside it proves overwrite-in-place across runs
   (bounded growth), not accumulation.

5. **Diff content, and expect the shape to vary by tool version.**
   md5 the strays against each archived copy. Older runs of the same bug can
   land at a *different depth* (no subdir at all) if the path had an optional
   component that was empty back then. Same bug, different footprint — report
   the invariant path RULE, not the one observed layout.

6. **Only now confirm in code.** `grep -n '<fn_name>' <file>` to count call
   sites; the arg at each site either is or isn't the bad root. Verify the
   claim's cited line numbers still match (files drift).

7. **Prove the negative separately.** For "nothing ever cleans this up", grep
   the whole tool for `rm|rmdir|unlink|prune|--delete` near the artifact name
   and confirm every hit is test-fixture setup, not a production path.

8. **Check the downstream consumers.** A grouping reader that keys on
   "every path segment between <artifact-dir>/ and the filename" turns the
   stray set into a bogus group; a reader that globs `run-*/` ignores it.
   Severity depends on this, not on the file count.

## Reporting
Give counts (k of n instances), the correlation that proves the caller, the
timestamp chain, and separate the mechanism (confirmed) from wording
refinements (e.g. "overwritten every run" is often really "at most one set
survives, but not rewritten on every run").
