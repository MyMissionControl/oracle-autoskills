---
name: git-index-lock-orphaned-by-killed-poll
description: Use when git add/commit dies on 'Unable to create .git/index.lock: File exists' under a tool that polls git status: prove the cause, fix via GIT_OPTIONAL_LOCKS=0 + safe lock reap
installer: auto-skill
created_at: 2026-07-25T22:01:56+00:00
created_session: 
trigger: error-recovery
created_by: claude
category: git
content_hash: 1344094f2f4d3187e5794e5e32387fe6b520b6aac4cffa46e90c83ff2535a42e
---
---
name: git-index-lock-orphaned-by-killed-poll
description: Use when `git add`/`commit` fails with "Unable to create '.git/index.lock': File exists" in a repo driven by a tool/UI that polls `git status` — diagnose the orphaned lock, prove the cause, and fix it at the source with GIT_OPTIONAL_LOCKS=0 plus a safe stale-lock reap.
---

# Orphaned `.git/index.lock` from a killed `git status`

## Why this happens (the non-obvious part)

`git status` is **not read-only**: it rewrites the index to refresh its stat cache, so it
**takes `.git/index.lock`**. Any wrapper that runs status with a kill-timeout
(`execFile({timeout})`, `timeout(1)`, a supervisor, a CI step limit) can SIGTERM git while it
holds that lock — leaving an **empty, permanently stale lock file** behind.

The nasty part: **`git status` keeps working with a stale lock present** (exit 0, correct
output). So the polling UI keeps reporting "N files to commit" while every `add`/`commit` in
that repo fails forever. Nothing surfaces the damage.

## 1. Confirm it is an orphan, not a live operation

```bash
R=<repo>
stat -c '%n size=%s mtime=%y' "$R/.git/index.lock"   # orphans are 0 bytes and OLD
pgrep -a git                                          # nothing running = nothing holds it
find <workspace-root> -maxdepth 6 -path '*/.git/*' -name '*.lock' \
  -exec stat -c '%y  %n' {} \;                        # look for a BATCH in one timestamp
```

A cluster of locks stamped within the same second across many repos = one parallel sweep got
killed. That is the signature of a poller, not of human git use.

## 2. Prove the mechanism before fixing (60 seconds)

```bash
cd "$(mktemp -d)" && git init -q -b main . && git config user.email t@t && git config user.name t
for i in $(seq 1 200); do echo x$i > f$i.txt; done && git add -A && git commit -qm init
touch f1.txt                                    # stat change only, content identical
b=$(stat -c %y .git/index); git status --porcelain >/dev/null; a=$(stat -c %y .git/index)
[ "$b" != "$a" ] && echo "plain status REWROTE the index → it took index.lock"
touch f1.txt
b=$(stat -c %y .git/index); GIT_OPTIONAL_LOCKS=0 git status --porcelain >/dev/null
[ "$b" = "$(stat -c %y .git/index)" ] && echo "GIT_OPTIONAL_LOCKS=0 → no index write, no lock"
echo hi >> f1.txt; : > .git/index.lock          # stale lock present
git status --porcelain >/dev/null && echo "status still OK (this is why the UI lies)"
git add -A                                      # fatal: Unable to create ... File exists
```

## 3. Fix at the source, in this order

1. **Read path: `GIT_OPTIONAL_LOCKS=0`** on every status/rev-parse/rev-list/remote/fetch call.
   Status then never takes an optional lock, so a killed poll cannot orphan one. Mandatory
   locks (`add`, `commit`) are unaffected — safe to set for the whole git wrapper.
2. **Write path: reap only a provably dead lock, then retry once.** Do not blanket-delete —
   deleting a live lock corrupts an in-flight index write. Stale means BOTH:
   - `mtime` older than a threshold (~30s), AND
   - no live `git` with the repo as cwd — on Linux scan `/proc/<pid>/comm == "git"` and
     `readlink /proc/<pid>/cwd == realpath(repo)` (`git -C <dir>` chdirs, so cwd matches);
     if `/proc` is unreadable, fall back to the age check alone.
3. **Raise the write timeout** (e.g. 8s → 60s). Killing `git add -A` mid-flight is itself a
   lock-orphaning event; a big worktree with a cold page cache exceeds a short timeout.
4. **Clean the existing orphans**: only when `size == 0` and hours old and no git is running.
   Then verify writability per repo with a real index write (`git add <file>` then
   `git reset -q <file>` restores the unstaged state). Beware: `git update-index --refresh`
   exits non-zero merely because a tracked file is dirty — that is NOT a lock failure.

## Tests that actually pin this down

Unit-test against real git in a temp repo (no mocks — the bug lives at the process boundary):

- write path reaps a backdated lock (`fs.utimesSync` to age it) and commits
- write path **refuses** a 1-second-old lock: returns the error, lock still present, HEAD unmoved
- the read path leaves `.git/index` mtime **unchanged** — this is the assertion that fails on
  the unfixed code, so it is the one that proves the fix

## Gotchas

- Deploying the fix into a long-running host (VS Code extension host, daemon) needs a
  **reload/restart** — recompiling output alone does not replace loaded code.
- Do not "fix" this by retrying the commit blindly, or by deleting the lock on every failure:
  both hide a real concurrent-write bug and can corrupt the index.
