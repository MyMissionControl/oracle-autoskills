---
name: commit-only-my-hunks-past-wip
description: 'Use when committing your change while the working tree (or same file) holds unrelated uncommitted WIP: stage only your hunks via a marker-filtered git apply --cached, prove it, commit index only.'
installer: auto-skill
created_at: 2026-07-20T09:09:11+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: git
content_hash: f11ebdd4210fac8d66179dfe15b7f2c16f85ad2acf3a5ed04cc0b3b3177c7494
edited_at: 2026-08-11T09:33:31+07:00
edited_by: skills-mcp
---
# Commit only my hunks when the file also has unrelated uncommitted WIP

Use when you must commit YOUR change to a tracked file, but `git status` shows the working tree ALSO holds unrelated uncommitted WIP (yours from another session, or a teammate's) — possibly in the SAME file. A plain `git add <file>` would sweep that WIP into your commit. This stages ONLY your hunks and proves it before committing.

## Steps

1. See the full picture:
   - `git status --short` — note which files are WIP (not yours).
   - `git --no-pager diff -- <yourfile>` — confirm which hunks are yours vs WIP.

2. Pick a MARKER string present in EVERY one of your hunks and in NONE of the WIP hunks (a new function name, a unique error string, a new var you added). Confirm the marker is absent from the WIP hunks.

   Then classify EVERY hunk and print the verdicts, so a miss is visible instead of silent:
   ```python
   import re
   parts = re.split(r'(?m)^(?=@@ )', open('/tmp/f.diff', encoding='utf-8').read())
   MINE = ("<marker1>", "<marker2>")
   for i, h in enumerate(parts[1:], 1):
       body = "\n".join(h.splitlines()[1:])
       print(i, "MINE " if any(k in body for k in MINE) else "OTHER", h.splitlines()[0])
   ```
   ⛔ **Then print the full body of any hunk whose verdict you are not certain of.** A diff
   carries only 3 lines of context, so a hunk that starts within a few lines of yours can be
   entirely theirs — line proximity proves nothing. Observed: an adjacent hunk 8 lines from
   mine was a UI change from the other session; only reading it settled it.

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

## Fallback: reconstruct the file when patching misplaces hunks

Step 4 relies on the patch carrying CONTEXT lines. If you reach for `git diff -U0` +
`git apply --cached --unidiff-zero` instead, know that `--unidiff-zero` disables context
matching and trusts the line numbers literally — so the moment you DROP a hunk, every
later hunk's anchor is off by the lines that hunk would have added, and git applies them
in the wrong place, **exits 0, and says nothing**. Observed: a `]`→`}` edit landed 14
lines early (invalid JSON), and an insert meant for an array landed after the file's last
function. Both looked fine until the staged diff was actually read.

When your hunks are non-contiguous, or a patch attempt already mangled the index, build
the exact content and write it straight into the index instead. The working tree is never
touched, so the WIP stays for its owner.

- Reset just that path first if needed: `git restore --staged <file>`
- Best source is YOUR working-tree file minus the WIP block — that is the version you
  actually compiled and tested:
  ```python
  s = open(p, encoding='utf-8').read()
  foreign = '''<the WIP block, verbatim>'''
  assert foreign in s                       # fail loudly if it moved
  s = s.replace(foreign, '', 1)
  assert '<wip-marker>' not in s and '<my-marker>' in s
  ```
- For JSON/YAML, build from `git show HEAD:<path>`, re-apply only your edits with a
  parser, and re-serialize so formatting stays canonical.
- Stage the result as a blob:
  ```bash
  SHA=$(git hash-object -w /tmp/staged-version)
  git update-index --cacheinfo 100644,$SHA,<path>
  ```
- Then re-parse it out of the INDEX to prove it is well-formed:
  `git show :<path> | python3 -c "import json,sys; json.load(sys.stdin)"`

## Prove the commit stands alone (before pushing)

Step 7 checks your code still works. Also check it does not silently DEPEND on the other
party's **untracked** files — that breaks the build for everyone else, not for you.
Export the index (tracked+staged only) and build it in isolation:

```bash
rm -rf /tmp/stagecheck && mkdir -p /tmp/stagecheck
git checkout-index -a --prefix=/tmp/stagecheck/
ln -s "$PWD/node_modules" /tmp/stagecheck/<subdir>/node_modules   # or install deps
(cd /tmp/stagecheck/<subdir> && <build / typecheck command>)
rm -f /tmp/stagecheck/<subdir>/node_modules && rm -rf /tmp/stagecheck   # unlink FIRST
```

Also `git fetch origin <branch>` before pushing — a shared checkout usually means a
shared remote, and the other session may have pushed while you worked.

## Notes
- **When you get to CHOOSE where your edit goes** (appending a doc bullet, a new list
  entry), place it **more than 6 lines away** from the nearest foreign change: git merges
  changes into one hunk once the gap is ≤ 2× the 3-line context, and a merged hunk cannot
  be filtered at all. Check with `git diff -U3 -- <file> | grep -c '^@@'` — expect one
  hunk per independent change. With them separated, "keep hunk N" by position is enough
  and you never need a marker.
- `git apply --cached` hunk line numbers are HEAD-relative; they apply fine as long as your hunks' context is unchanged from HEAD (true when the WIP touches disjoint regions of the file). This is why step 4 uses a normal context diff, NOT `-U0`.
- Read the staged diff itself (`git diff --cached -U2 -- <file>`), not just `--stat`. A misplaced hunk is obvious in the hunks and invisible in the stat.
- If a hook mangles `git commit`/`push` (an RTK-style rewriter), run them via the raw proxy: `<proxy> git commit -F <msgfile>` / `<proxy> git push`.
