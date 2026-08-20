---
name: edit-code-a-live-process-is-reading
description: 'Use when the file to edit is executed live or the installed path is a symlink into the repo: worktree + baseline + red-proof, and hold the merge.'
installer: auto-skill
created_at: 2026-08-20T15:57:01+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'workflow'
content_hash: 2394e214b14ec7f11a7a34e772cb07d235fdda6c14b3337158a37e3ec9465a6c
---
# Change code that a running process is reading right now

Use when the file you must edit is being executed live (an agent/daemon re-reads a script on
every call), or when the "installed" copy is a **symlink into the repo** — editing the repo
then changes production mid-flight. Applies to `~/.<tool>/…` → repo symlinks, plugin dirs,
skill dirs, cron scripts.

## 1. Prove whether your edit is live before you type

    readlink -f <installed-path>          # symlink into the repo? then repo == production
    md5sum <installed> <repo-copy>        # same hash = same file, not a copy
    pgrep -af '<runner>'                  # who is executing it now

A long shell script is read **incrementally** by `bash`, so replacing it while a call is in
flight can corrupt that call. "Behaviourally identical" is not the same as "safe to write".

## 2. Develop in a git worktree, never in the checkout the runtime points at

    git -C <repo> worktree add -b <branch> /tmp/wt-<short>
    # edit + test only inside /tmp/wt-<short>; the live tree keeps its old bytes

Verify at the end: `md5sum <installed>` must equal the pre-change hash you recorded.

## 3. Baseline the tests in the worktree BEFORE editing

Run every suite you plan to touch and write the numbers down. Without a baseline you cannot
tell your own breakage from pre-existing failures — and you cannot tell **skips** from passes.

## 4. Red-proof new tests against the pre-change code

Tests written after the fix prove nothing until you watch them fail:

    mkdir -p /tmp/mut/<pkg>; git -C /tmp/wt-x show HEAD:<path-to-file> > /tmp/mut/<pkg>/<file>
    cp /tmp/wt-x/<tests>/*.sh /tmp/mut/<pkg>/tests/; ln -s /tmp/wt-x/<tests>/fixtures /tmp/mut/<pkg>/tests/fixtures
    bash /tmp/mut/<pkg>/tests/<suite>.sh        # every NEW assertion must fail here

## 5. Hold the merge; hand the decision over

Report: branch name, commits, test deltas, red-proof, and the one risk left (the write itself).
Let the owner pick the moment. Keep the worktree until they land it.

## Traps that cost real time

- **Isolated tmux needs a SHORT socket path.** `TMUX_TMPDIR=<long scratch path>` fails with
  "File name too long" (unix socket ≈104 chars) and `tmux new-session` dies silently → every
  tmux-dependent test prints `(skip …)` and the suite still says 0 fail. Use `/tmp/<8 chars>`.
- **`pkill -f "<pattern>"` matches your own shell** (your command line contains the pattern) and
  kills it — exit 144. Collect PIDs with `pgrep -a`, then `kill <pid>`.
- **A suite that skips is not a suite that passes.** Compare the pass COUNT to the baseline, not
  just "0 fail"; a big jump after fixing isolation (e.g. 98 → 134) is the skips coming back.
- **Shared state late in a test file.** Appending cases at the end inherits whatever earlier
  cases left in env/dirs (a guard test may point a path at garbage on purpose). Give your block
  its own temp dirs and pin its env explicitly.
