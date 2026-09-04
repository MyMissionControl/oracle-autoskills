---
name: verdict-function-for-store-sharing
description: 'Use when writing a reusable check that classifies a tree as sharing-vs-copied against a content-addressed store (pnpm/uv/nix/ccache): five ways such a verdict silently lies, plus rc states and…'
installer: auto-skill
created_at: 2026-09-04T14:15:37+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude'
category: 'measurement'
content_hash: ea0bb0f5a8ea1fa111af889a42d6b0ed20806228fae99e6113c75f7e2fd3b041
---
# Write a store-sharing verdict that does not lie

Use when you must ship a **reusable check** that classifies a tree as *sharing* vs *copied*
against a content-addressed store — a package-manager store or cache (pnpm store, uv cache,
Go/Cargo module cache), a nix store, ccache, a build-artifact cache — and something downstream
acts on the answer (a receipt written for later audit, a gate, a "run this to fix it" hint).

A one-off spot check is easy. A **function** is where the lying happens: I shipped one whose
own tests were green, and an adversarial review reproduced `VERDICT=shared` on a tree that was
**1.2% shared**. Five specific ways the verdict goes wrong, all of which pass naive tests.

## 1. nlink is a prefilter, never the verdict

`st_nlink > 1` only says "this file is hardlinked to something". A tree can be hardlinked to
**itself** (`cp -al`, `rsync --link-dest`, duplicate payloads inside one archive): measured
99.53% `nlink>1` with **zero** inodes intersecting the configured store.

The verdict is the `(st_dev, st_ino)` intersection with **the store you resolved**, not any
store. Use `nlink>1` only to skip the store walk entirely when no file could possibly match —
that early exit is what makes the check cheap on the common negative.

## 2. The denominator must be what you inspected, not the prefilter's size

    need = len(sample) // 2      # WRONG — sample is the nlink>1 subset
    need = max(1, total // 2)    # what you actually walked

With the first form the bar collapses as sharing falls: a tree with ONE hardlinked file needs
ONE confirmation. Reproduce this before you trust any ratio-based verdict — build a fixture
with `n_plain=300, n_shared=1` and assert the answer is *copied*.

## 3. Count distinct inodes, not matching paths

Content-addressed stores **deduplicate**: one inode legitimately sits at several store paths.
Measured on a real uv cache: 105,459 files, 34,211 distinct `nlink>1` inodes, **69% present at
more than one path, max 4**. A loop doing `hits += 1` per matching path inflates the numerator
up to 4x off a single genuinely-shared file. Accumulate into a set of `(dev, ino)` and compare
`len(hits)`.

## 4. Exclude metadata the installer always writes itself

Every installer writes per-install files that can never come from the store (for Python wheels:
`RECORD`, `INSTALLER`, `REQUESTED`, `direct_url.json`, plus venv scaffolding). Leave them in the
denominator and a **small** tree hits a hard ceiling: measured exactly 50% for a one-package
tree (10 files, 5 from the store, 5 installer-written) — so any "≥50%" bar is decided by
metadata overhead rather than by sharing. Identify the equivalent set for your ecosystem and
skip those names in both numerator and denominator.

## 5. "Cannot determine" is a third answer, and it must not be the negative one

Fold *store path unknown*, *store dir missing*, *interpreter/tool absent*, *tree exists but
holds zero payload files* into the "not shared" branch and the check reports **copied, wasting
N MB** — together with whatever destructive remediation the receipt prints (`rm -rf …`) — on a
machine that simply has no store, or on a tree where the install failed and nothing is there.

Return at least four states and make the caller handle them:

    0 shared        evidence collected, threshold met
    1 copied        evidence collected, threshold not met
    2 undetermined  store/tool/permissions unknown  -> caller must stay SILENT
    3 empty         tree exists, zero payload files -> "not installed yet", not "copied"

A receipt that cannot be computed must print nothing. A wrong receipt is worse than no
receipt, because the receipt is usually the only artifact a later audit has.

## Do not trust the tree's self-description

A marker saying which tool built the tree (`pyvenv.cfg`'s `uv = <ver>`, a `packageManager`
field, a lockfile) answers "who created this", never "where did the bytes come from". The
counter-example is one command away: create with the fast tool, then install with
`--link-mode=copy` (or plainly with the other tool) — every marker present, sharing 0%.

## Validate with hand-built fixtures, then against ground truth

Network-dependent fixtures make the suite slow and flaky, and a real install gives you no
control over the ratio. Generate trees programmatically — `n_plain`, `n_shared`,
`dup_paths_per_inode`, `with_metadata` — so each of the five failures above gets its own
deterministic case, including the adversarial mixed tree (mostly copied + a few shared).

Then run the finished function against every real tree whose truth you measured independently
and require it to agree on all of them. Getting 4/4 on real trees is what tells you the
stricter threshold did not flip the genuine positives.

## Two test-harness traps that made my own suite lie

- **A verb that reports on stdout usually exits 0 regardless.** `if f; then echo YES; else echo
  NO; fi` returns `echo`'s status, so a helper reading `$?` reports success for every input.
  Read stdout, and have such a verb print all the states from §5 rather than a boolean.
- **Asserting a token exists anywhere in the file is vacuous** when a sibling implementation
  already contains it. Extract the specific function (or template block) and assert inside it.
- **A fixture pointing at a store directory that was never created** yields *undetermined*,
  which then reads as "the code broke". `mkdir` the store in the fixture.
