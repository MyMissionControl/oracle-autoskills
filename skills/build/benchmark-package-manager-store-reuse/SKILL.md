---
name: benchmark-package-manager-store-reuse
description: 'Use when choosing a package manager on the claim that a shared store makes the 2nd install seconds: arms, fake-fast guards, nlink/inode/md5 receipts.'
installer: auto-skill
created_at: 2026-08-29T12:51:07+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude'
category: 'build'
content_hash: 7bf9f244eb66e4c2afd780c9e6b7d45f651ec1e92b4f18d0c4779720fdc386b1
edited_at: 2026-09-04T14:14:54+07:00
edited_by: skills-mcp
---
# Prove whether a package manager's store actually reuses compiled artifacts

Use when deciding between package managers / runtimes on the claim "the second project
installs in seconds because the store is shared". The claim is testable in ~15 minutes and
the naive test lies in four specific ways.

## Build the fixture from a real project, not a toy

Copy `package.json` + the existing lockfile (+ any dir a postinstall needs, e.g. a prisma
schema) from a project that HAS a native dependency into a throwaway dir. A toy fixture with
pure-JS deps cannot show the effect you are measuring — the whole cost is the native build.

## Arms that actually answer the question

Same fixture, one runner per arm, serial (never parallel — they fight over the shared store
and the CPU, and the timings become noise):

    A0  <pm> install --ignore-scripts     # extract-only floor
    A1  <pm> install                      # baseline
    B1/B2  <alt-pm>, 1st dir then 2nd dir # does IT reuse anything?
    C1/C2  <candidate>, 1st then 2nd dir  # <-- the decisive pair
    D1  baseline on the newer runtime     # the rival fix, often cheaper than switching pm

`C1` pays for populating the store; `C2` in a DIFFERENT directory is the steady-state number.
Report both — quoting only the warm number oversells it.

## Four traps that produce a confident wrong answer

1. **`require('<pkg>')` does not load the native addon** in many packages (it loads lazily on
   first construction). A "loads OK" check that only requires the module passes even when the
   `.node` file is absent. Construct the object and run a real operation:
   `new Db(':memory:'); db.prepare('select 1').get()`.
2. **A fast install with no artifact is the "fake fast" failure.** Modern managers block
   dependency lifecycle scripts by default (allowlist fields differ per manager and per major).
   Assert the artifact exists AND works in every arm, or the arm's time is meaningless.
3. **`du` stops being a measure once files are hardlinked.** Per-tree `du` sums can RISE while
   real free space falls. Read `df` for the disk question; use `du -s` vs `du -s --count-links`
   for the in-tree sharing, and `stat -c %h` (nlink) for cross-tree sharing.
4. **A bare environment changes the result.** Under `env -i` a prebuilt-binary downloader can
   fail and silently fall back to a full source compile — which is also what a CI container
   does. Run one arm with a realistic minimal env and report it separately; it is the CI number.

## Prove reuse, do not infer it from the clock

Three independent receipts, all cheap:

    stat -c 'nlink=%h inode=%i size=%s' <artifact>   # nlink>1 = CANDIDATE ONLY, never the verdict
    find <store> -inum <inode>                       # the inode is IN the store = reuse

**`nlink>1` alone is not evidence of store reuse** and treating it as the verdict has already
produced a confident wrong answer twice: a tree measured 99.53% `nlink>1` with **zero** files
whose inode intersected the configured store — the tree was hardlinked to ITSELF (a `cp -al`,
an `rsync --link-dest`, duplicate payloads inside one archive). Only the `(st_dev, st_ino)`
intersection with the store you actually configured is a verdict; `nlink` is a cheap prefilter
that tells you which files are worth looking up. If you are writing this as a reusable
verdict function rather than a one-off check, see `verdict-function-for-store-sharing`.
    md5sum <artifact>; md5sum <same file built locally elsewhere>   # identical = real build output

Also grep the install log for the compiler (`node-gyp`, `gyp info`, `cc1plus`): zero hits plus a
present artifact is the signature of a cache hit.

## Before recommending the winner, check the store's own address

Print the resolved store path. A store living under a versioned/revisioned directory (a snap or
per-release app dir) is orphaned by the next update of that app, silently costing a full
re-download. Pin it explicitly and re-verify from a clean shell.

## Layout matters as much as speed

If the candidate uses an indirect layout, measure: symlink count per tree, and whether a
transitive dependency resolves from the project root. A flat/hoisted mode often keeps the store
sharing (verify with nlink) while removing both the resolution surprise and the symlink count
that breaks archive-based deploys. Do not assume hoisting costs the dedupe — measure it.
