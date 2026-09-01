---
name: refute-concurrent-file-outage
description: 'Use when refuting/confirming a claim that a build or install tool destroys files a concurrent reader needs: strace histogram, path-resolution census, cache-purging probe, and a scale control that…'
installer: auto-skill
created_at: 2026-09-01T17:16:15+07:00
created_session: 
trigger: 'complex-task'
created_by: 'verifier-subagent'
category: 'verification'
content_hash: c265aa93071604d526c29e2d8fd8e90e392d095b318f0d8e33f08113f8120be6
---
# Refuting a "tool X destroys files a concurrent reader needs" claim

Use when someone claims a build/install/codemod tool is destructive to a live
reader (ENOENT window, "it deletes and re-creates everything"). Prose probes
overstate the mechanism and understate the magnitude. Settle it in four moves.

## 1. Syscall truth first — separate "unlink every file" from "one atomic rename"

    strace -f -tt -qq \
      -e trace=unlink,unlinkat,rename,renameat,renameat2,rmdir,link,linkat,mkdir,mkdirat,symlink,symlinkat \
      -o trace.log <tool> <args>
    grep -oE '\b(unlink|unlinkat|rename|renameat|link|symlink|rmdir)\(' trace.log | sort | uniq -c | sort -rn

A histogram of `unlink` ~= 0 next to thousands of `link` means the tool BUILT a
new tree beside the old one and swapped a handful of directories with atomic
`rename()`. That is a *visibility* outage, not destruction. Classify the unlinks
by path prefix before believing "every file": shim/bin dirs and `*_tmp_*`
staging files dominate.

## 2. Prove nothing was destroyed — path-resolution census, not inode equality

Snapshot every path before, re-stat every path after:
  - GONE (path no longer resolves) is the only number that means destruction.
  - "different inode" does NOT mean destroyed: the path may now resolve through
    a new symlink into a store, with the original still on disk under a
    quarantine dir. Report SAME / DIFFERENT / GONE separately.

## 3. Measure the window with a probe that cannot lie

A probe that reports `failures=1` almost always forgot to purge the module
cache — a cached module never touches disk again, so the outage becomes
invisible after the first tick. Per tick: purge the cache, re-resolve, AND stat
a few hundred real paths. Record first/last miss timestamps, not just a count.
Run the config the *product* actually uses, not the tool's default — a linker /
strategy flag can take require-failures to zero while stat-misses remain.

## 4. Kill the linear extrapolation with a scale control

"1.1s at 8.8k files therefore ~7s at 55k files" is a model, not a measurement.
Falsify it cheaply: inflate the pre-existing tree with junk files to the real
project's size and re-run the identical experiment. If the window barely moves,
it is bounded by the tool's own work (resolve+link the NEW graph), not by the
old tree's size, and the extrapolation is dead.

## 5. Then ask whether the code path even exists

Grep every call site of the destructive command in the shipped code. A rule may
be sound while the hazard is off-path: gated behind `[ ! -d <dir> ]`, or the
tool is only ever invoked in a `--lockfile-only` / `--dry-run` mode. Run the
observer over the REAL sequence the product issues and report that number too.

## Reporting

Separate four verdicts the claimant fused into one: mechanism, magnitude,
scaling, and reachability. A claim can have a real phenomenon and still be
wrong on all four. Note which parts were labelled "measured" but were actually
inferred from a downstream symptom.
