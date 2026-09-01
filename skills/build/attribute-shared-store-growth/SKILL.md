---
name: attribute-shared-store-growth
description: 'Use when a claim attributes growth (or zero growth) of a shared content-addressed store to one build step: mtime-bucket attribution, tool counters, files-vs-cache section identity, and a…'
installer: auto-skill
created_at: 2026-09-01T18:04:45+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'verifier-adversarial'
category: 'build'
content_hash: 5f9a6d78ab8ff860f49b0eeeefa917c7558dc7f2e8810892691e72110ee0483d
---
# Attribute growth of a shared package/content store to a cause

Use when someone claims "step X grew the shared store by N bytes" or "step X costs 0"
for a content-addressed store (pnpm store, uv/pip cache, nix store, ccache, buildkit).
Two traps make the naive version wrong in opposite directions.

## 1. Never trust a `du` delta taken around a step on a SHARED store
A global store is written by every concurrent job on the box. A before/after `du -sb`
pair only bounds *total* growth in that window, it does not attribute it.
`du -sb` IS hardlink-aware inside one invocation, so repeated `du` on the SAME tree is
fine; the failure is attribution, not double counting.

Attribute by mtime bucket instead — this names the exact minute and file count:
```
python3 - <<'PY'
import os,datetime,collections
root='<STORE>'; b=collections.Counter(); c=collections.Counter()
for d,_,fs in os.walk(root):
    for f in fs:
        p=os.path.join(d,f)
        try: st=os.lstat(p)
        except OSError: continue
        k=datetime.datetime.fromtimestamp(st.st_mtime).strftime('%Y-%m-%d %H:%M')
        b[k]+=st.st_size; c[k]+=1
for k,v in b.most_common(15): print(k,v,c[k])
PY
```
Then correlate that minute against per-tree file mtimes (INCLUDE node_modules /
build dirs — that is where the evidence is) to see which tree was actually installing.

## 2. Read the tool's own counter before inventing a mechanism
Package managers print what they did. pnpm's `reused N, downloaded M, added K` and
`Packages: +A -B` lines decide "downloaded" vs "rebuilt from cache" for free.
A claim that growth is *build output* dies instantly if the log says `downloaded M>0`.

## 3. Content check: does the bytes' IDENTITY match the claimed mechanism?
Map each new content file back to the store index and record WHICH SECTION cites it
(normal package `files` vs a build/side-effects cache section).
- Foreign-platform artifacts (`*.dll`, `*.exe`, `*.dylib`, `*-darwin-*`, `*-win32-*`,
  `*android*`, `*openbsd*`) can NOT be local build output on a Linux box. Their presence
  proves cross-platform optional-dependency fetching, not a build cache.
- Also total the build-cache section separately and check its mtimes. "The cache
  populated today" is refuted if the newest byte in it is days old.

⛔ TRAP that gave me a wrong intermediate answer: pnpm stores executable files under the
same content hash plus a **`-exec` suffix**. Keying by the raw filename leaves every
native binary "unattributed" (for me: 205 MB / 22 files) and can hide the whole answer.
Strip the suffix before lookup: `if key.endswith('-exec'): key = key[:-5]`.

## 4. The only valid A/B: one COLD store per arm
Two trees sharing one global store cannot be compared — whichever runs second finds it
warm and always shows ~0. That control is vacuous no matter how the logs read.
Give each arm its own store via config (for pnpm: `store-dir=<path>` in the tree's
`.npmrc`; a `--store-dir` FLAG is rejected by some subcommands like `pnpm import` and
will silently skip the step, so prefer the config file), start both cold, and compare.
Byte-identical deltas across arms = the arm is not the cause.

## 5. Then bisect the real trigger with one more arm
Once you can reproduce, flip ONE setting per arm. Config the tool itself injects into
the project is a prime suspect — check the generator's source for what it writes into
`.npmrc`/`.cfg`, and diff an arm with that line removed. A "budget N GB, it's inherent"
conclusion collapses if the default setting costs 0.

Use a MINIMAL fixture that still pulls the same shape (one dep with many
platform-specific optionals + one postinstall) — full app trees cost GBs per arm and
you need several arms. Check `df -h` first and delete the stores when done.
