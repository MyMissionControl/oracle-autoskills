---
name: commit-only-my-hunks-past-wip
description: Use when committing your change while the working tree (or same file) holds unrelated uncommitted WIP: stage only your hunks via a marker-filtered git apply --cached, prove it, commit index only.
installer: auto-skill
created_at: 2026-07-20T09:09:11+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: git
content_hash: 374edcb2d3619614e53e9a85953891d05827b25c3ecfaf6ca9744bc592c210c2
---
# Commit only my hunks when the file also has unrelated uncommitted WIP

Use when you must commit YOUR change to a tracked file, but `git status` shows the working tree ALSO holds unrelated uncommitted WIP (yours from another session, or a teammate's) — possibly in the SAME file. A plain `git add <file>` would sweep that WIP into your commit. This stages ONLY your hunks and proves it before committing.

## Steps

1. See the full picture:
   - `git status --short` — note which files are WIP (not yours).
   - `git --no-pager diff -- <yourfile>` — confirm which hunks are yours vs WIP.

2. Pick a MARKER string present in EVERY one of your hunks and in NONE of the WIP hunks (a new function name, a unique error string, a new var you added). Confirm the marker is absent from the WIP hunks.

3. Stage the files that are fully yours (no WIP) normally: `git add <clean-file> ...`

4. For a file that mixes your hunks + WIP, filter and stage only your hunks via `git apply --cached`:
   - Take `git diff -- <file>`, split into the header + each `@@` hunk.
   - Keep only hunks whose body contains the MARKER; concatenate header + kept hunks into a patch file.
   - `git apply --cached --whitespace=nowarn <patch>`  (updates the INDEX only; working tree untouched, so the WIP stays for its owner).
   - A tiny python script is the reliable splitter; `git add -p` is interactive and often unavailable in headless harnesses.

5. PROVE the staged set is clean BEFORE committing:
   - `git --no-pager diff --cached --stat`
   - `git --no-pager diff --cached | grep -c <MY-MARKER>` → must be > 0
   - for each WIP marker: `git --no-pager diff --cached | grep -cF <WIP-MARKER>` → must ALL be 0

6. Commit the INDEX only — NEVER `git commit -a` (that re-stages tracked WIP):
   - `git commit -F <msgfile>`
   - `git status --short` → confirm WIP files still show modified (untouched).

7. Verify the COMMITTED state independently. The working tree still has WIP mixed in, so a working-tree test run does NOT prove the committed code. Extract HEAD versions to a temp mirror and run the tests there:
   - `git show HEAD:<path> > /tmp/v/<path>` for the changed file + its tests, then run.
   - Watch for harness confounds: e.g. exporting GIT_AUTHOR_* can override author-provenance a test asserts, faking a failure. Cross-check by running HEAD~1 the same way — if it "fails" identically, it's an env artifact, not your regression.

## Notes
- `git apply --cached` hunk line numbers are HEAD-relative; they apply fine as long as your hunks' context is unchanged from HEAD (true when the WIP touches disjoint regions of the file).
- If a hook mangles `git commit`/`push` (an RTK-style rewriter), run them via the raw proxy: `<proxy> git commit -F <msgfile>` / `<proxy> git push`.
