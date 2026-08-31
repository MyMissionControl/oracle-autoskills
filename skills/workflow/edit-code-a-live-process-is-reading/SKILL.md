---
name: edit-code-a-live-process-is-reading
description: 'Use when the file to edit is executed live or the installed path is a symlink into the repo: worktree + baseline + red-proof, and hold the merge.'
installer: auto-skill
created_at: 2026-08-20T15:57:01+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'workflow'
content_hash: bd5ae6c82e64e9ca95e7ce55ad8638c31613cb03e192606d6ef4cd00395ea59b
edited_at: 2026-08-31T10:26:39+07:00
edited_by: skills-mcp
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

A long shell script is read **incrementally** by `bash` — but that only bites you if the write
truncates the **same inode**. Know which kind of write you are about to do:

    stat -c %i <file>                     # before and after: inode CHANGED = in-flight calls safe

- **Safe (new inode):** `git checkout` / `git merge` / `git stash pop`, `sed -i`, `mv tmp file`,
  anything that renames a temp over the target. The running `bash` still holds an fd on the old
  inode and finishes reading the OLD bytes; only calls started AFTER the write see the new code.
  Measured 2026-08-20: inode 1611330 → 1614154 across a `git merge`, and a script sleeping
  through the merge still printed its old last line.
  ⛔ **But the inode test is NOT a reliable safety signal — do not gate a merge on it.**
  Measured 2026-08-31 on the same repo: `git merge --ff-only` of a 1.2 MB script changed the
  content (md5 46ba558… → be73ad2…, 12793 → 12879 lines) while the inode stayed 3171851.
  Either git wrote in place, or ext4 immediately reused the freed inode number — you cannot tell
  from `stat` which happened, so "inode unchanged" does not prove an unsafe in-place write and
  "inode changed" does not prove a safe rename. Get your safety from the two things you CAN
  control: (a) do the work in a worktree so the live tree is untouched until you choose to land,
  and (b) check the cross-invocation contract (§1 last paragraph). If a call really must not see
  new bytes mid-flight, copy the script to a temp path and run that copy.
- **Unsafe (same inode):** `> file`, `cat new > file`, `tee file`, `dd conv=notrunc`, an editor
  configured to write in place. These are what corrupt a call in flight.

So "wait for the fleet to go idle before merging" is usually cargo cult — prove it with `stat`
instead of assuming. What a mid-flight swap CAN break is a **cross-invocation contract**: verb A
(old code) writing state that verb B (new code) reads differently. Check that, not the bytes.

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

Report: branch name, commits, test deltas, red-proof, and the one risk left. Let the owner pick
the moment — because landing production code is **their** call, not because the write is unsafe
(see §1). Before handing over, do the two checks that make "ready" honest:

    git -C <repo> worktree add -q -b trial/merge /tmp/trial main   # throwaway
    cd /tmp/trial && git merge --no-edit <A> && git merge --no-edit <B>
    git diff --name-only --diff-filter=U      # empty = no conflicts
    # then run every touched suite ON THE MERGED TREE, not just per-branch

Two branches that each merge cleanly can still be broken together. Delete the trial worktree
and branch afterwards; keep the dev worktree until the owner lands it.

**Also state the marker/flag that gates your fix.** A feature behind an opt-in file or env
default does nothing for existing installs — "merged" then reads as "fixed" when nothing changed.
Say plainly which existing targets need the flag turned on.

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
