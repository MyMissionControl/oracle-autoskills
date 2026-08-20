---
name: graft-files-onto-fork-live-branch
description: 'Use when a fork has work stranded on a too-diverged branch: graft only the missing files via a temp worktree, test against the target branch, and record them in a machine-readable FORK-NOTES…'
installer: auto-skill
created_at: 2026-08-19T10:54:21+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'git'
content_hash: 7a09bfccbe73ee9240fd97aa6c9a83ed6474e6f9b29105be46f813ee92ca7621
---
# Graft files from a diverged branch onto a fork's live branch

Use when a fork has work stranded on a local branch that is too diverged to merge, and
you must land only the files the live branch lacks — then make sure a future clone knows
those files are yours, not upstream's.

## 0. Establish the shape before touching anything

```bash
git -C <repo> remote -v                       # which remote is origin, which is upstream
git -C <repo> rev-parse --abbrev-ref HEAD     # what is checked out RIGHT NOW
git -C <repo> rev-list --left-right --count origin/<live>...<stale>   # behind / ahead
git -C <repo> config --get branch.<live>.remote                      # push-trap check
gh repo view <owner>/<repo> --json defaultBranchRef -q .defaultBranchRef.name
```

Four traps this surfaces:

- **Diverged lineage, not a near-neighbour.** A huge behind-count (e.g. 1141 behind /
  131 ahead) means the two branches descend from different upstream lines. **Do not
  merge.** Graft files.
- **`branch.<b>.remote` = `upstream`.** Then a bare `git push` targets the upstream
  org, and git's own error text *suggests* the wrong command. Always
  `git push origin <local>:<remote>`, with `--dry-run` first — read the dry-run output
  and confirm it says the fork's URL.
- **origin's default branch is not the live branch.** Then `git clone` with no
  `--branch` silently gives code nobody runs. Verify per repo; do not assume.
- **The working tree may be live.** If a global dev-linked binary resolves into it
  (`readlink -f $(which <cli>)`), switching its branch changes what the machine
  executes. Never `git checkout` there.

## 1. Build the commit in a throwaway worktree

```bash
git -C <repo> worktree add -b <graft-branch> /tmp/<name> origin/<live>
git -C <repo> rev-parse --abbrev-ref HEAD    # prove the real checkout did NOT switch
```

Copy each file out of the stale branch by content, not by cherry-pick:

```bash
mkdir -p /tmp/<name>/$(dirname <path>) && git -C <repo> show <stale>:<path> > /tmp/<name>/<path>
```

Confirm per file that it is genuinely absent from the target
(`git cat-file -e origin/<live>:<path>`), and check for content damage the stale
history may carry (`tr -dc '\000' < f | wc -c` for stray NUL bytes).

## 2. Test the graft against the TARGET branch's own code

This is the step that is actually in question: the tests were authored against the
stale branch, possibly thousands of commits away. Deps are missing in a fresh
worktree, so borrow them from the real checkout **only when both sit on the same
commit** — verify first, and remove the symlink before committing:

```bash
[ "$(git -C <repo> rev-parse HEAD)" = "$(git -C /tmp/<name> rev-parse HEAD)" ] &&
  ln -s <repo>/node_modules /tmp/<name>/node_modules
cd /tmp/<name> && <test-runner> <test-path>          # must pass HERE, not on the stale branch
rm /tmp/<name>/node_modules
```

If it fails on a missing package, that is the harness; if it fails on an API or schema
mismatch, the graft is not viable as-is — report that instead of forcing it.

## 3. Record what is yours, machine-readably

Add `FORK-NOTES.md` at the repo root with: which remote to push to, the live branch
name, the push trap, local-only history that no remote holds (branches, and count the
tags — `git ls-remote --tags origin | wc -l` is often 0 while hundreds exist locally),
and a **marker-delimited manifest**:

```
<!-- fork-notes:added-files -->
    path/one.ts
    path/two.test.ts
<!-- /fork-notes:added-files -->
```

⛔ One path per line inside markers. Never let a loader grep the prose: a bullet that
names two files on one line loses one silently, and the announcement then under-reports
forever. Read it with
`sed -n '/<!-- fork-notes:added-files -->/,/<!-- \/fork-notes:added-files -->/p'`.

## 4. Teach the loader to announce it

In whatever script clones the project, after each clone: read the manifest, print each
path, and **verify the path exists in the clone**. A missing path means the clone landed
on the wrong branch — so the announcement doubles as a wrong-branch detector for free.
Also make the loader pin `--branch <live>`, add the `upstream` remote with
`git remote set-url --push upstream DISABLED-...`, and set `branch.<live>.remote=origin`.

Test all three paths before believing it: normal, listed-file-missing, empty-manifest.
Each must fail loudly.

## 5. Land it and clean up

Separate commits per concern (graft / notes / unrelated ignore-file fix) so each is
independently revertable. `--dry-run` the push, read the remote URL in the output, then
push with an explicit refspec, PR against the live branch, merge `--rebase` (the graft
branch sits directly on the live tip, so it fast-forwards).

```bash
git -C <repo> merge --ff-only origin/<live>     # bring the real checkout up, additive only
git -C <repo> worktree remove /tmp/<name>
git -C <repo> branch -D <graft-branch>
git -C <repo> worktree list                     # confirm only the intended worktrees remain
```

⛔ Before removing any leftover worktree, check whether something imports it by absolute
path (`grep -rl <worktree-path> ~/.claude ~/.config`) — some are load-bearing.

## What this does NOT do

Grafting files does not reduce `git rev-list --all --not --remotes --count`: the stale
commits still exist only locally. If the goal is that number reaching 0, push the stale
branch as a preservation ref (`git push origin <stale>:refs/heads/archive/<stale>`)
as a separate decision, and push tags too.
