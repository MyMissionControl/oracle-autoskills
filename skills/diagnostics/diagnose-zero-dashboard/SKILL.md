---
name: diagnose-zero-dashboard
description: 'Use when a tool/dashboard shows 0 or empty with no error: trace the live process env and path chain to the swallowed error, then validate any fix by running the vendor''s own reader and splitting…'
installer: auto-skill
created_at: 2026-08-31T12:17:23+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude'
category: 'diagnostics'
content_hash: 81ec25c57ffe26692103b845257dc80685f27cae696ba1e380a3bda39817602a
---
# Diagnose a tool that reports zeros instead of an error

Use when a dashboard, report, or panel shows `0` / `$0` / empty lists but no error, and
you suspect it is reading the wrong place rather than computing wrongly. Also covers the
decision of whether to wire the real data in.

## 1. Read the LIVE process env, never the launcher code

The launcher may be one of several paths, and a wrapper may override it. Get the truth
from the running process:

    PID=$(ss -lptn 'sport = :<port>' | grep -oP 'pid=\K[0-9]+' | head -1)
    tr '\0' ' ' < /proc/$PID/cmdline; echo
    tr '\0' '\n' < /proc/$PID/environ | grep -E '^(HOME|XDG_.*|.*_CONFIG_DIR|.*_HOME)='

A sandboxed/caged `HOME` is the single most common cause: the tool resolves
`os.homedir()/<subdir>` and lands somewhere empty. Note which override vars are
*absent* — that is what proves the fallback branch was taken.

## 2. Walk the path resolution chain and print each hop

Find the resolver (`getConfigDir`, `getDefaultDir`, …) and follow it literally. Each hop
is usually a plain `path.join`. Write the chain out as a table with the resolved value at
every step, then `ls -la` the final path. "No such file or directory" is the finding.

## 3. Find the swallowed error

Zeros-with-no-error nearly always means a caught error turned into an empty result:

    grep -n "catch" <reader>.js        # then read each one
    # look for:  catch { return []; }   catch { return {}; }   catch {}

Cite the exact `file:line`. This is what makes "missing directory" indistinguishable
from "no data" in the UI, and it is the real reason nobody noticed.

## 4. Before wiring the real data in, RUN THE VENDOR'S OWN READER on it

Do not assume that pointing the tool at real data yields a correct number. Prove it in a
scratch sandbox first:

    S=<scratchdir>; mkdir -p $S/home
    ln -s <real-data-dir> $S/link          # symlink the DIR is fine: readdir resolves it
    HOME=$S/home nice -n 19 /usr/bin/time -f "wall=%es peakRSS=%MkB" \
      node -e "require('<vendor>/dist/<reader>.js').loadAll({dir:'$S/link'}).then(r=>...)"

Two traps:
- **Sampling with symlinks silently yields zero.** `readdirSync(dir,{withFileTypes:true})`
  + `entry.isDirectory()` is FALSE for a symlinked subdir. Symlink the TOP dir (resolved
  by path lookup) or **hardlink** individual files to build a size-bounded sample.
- Build a size-bounded sample by hardlink to measure throughput cheaply, then extrapolate
  and confirm memory with the few largest files (a streaming parser keeps RSS flat; a
  slurping one does not — that is the OOM question, answer it before the full run).

## 5. Compare TOKENS/COUNTS, not just the money

When the vendor's number disagrees with your known-good number, compute both ratios:

    vendor_total / known_total      for the priced value (money)
    vendor_units / known_units      for the raw counts (tokens, rows, bytes)

- **Ratios equal** -> the rate tables agree; the difference is *counting*. Look for
  missing de-duplication (`grep -c requestId`, `message.id`, `new Set`) in the vendor's
  reader. Zero hits = it double-counts every re-logged record.
- **Ratios differ** -> the difference is *pricing*; compare per-category rate tables.

This single split turns "the numbers disagree" into a named, citable cause in one step.

## 6. Then decide — a plausible wrong number is worse than an obvious zero

If the vendor's reader is provably wrong (no dedup, stale rates), wiring the real data
converts an *obviously broken* `0` into a *believable* wrong value. Recommend against it,
and instead make your own UI say why the vendor's page is empty. Reserve the wiring for
when step 4-5 shows the vendor's total actually matches.

## Notes
- Never patch vendor code to fix this; prove it untouched when asked:
  `find <vendor> -newermt '<install time>' -type f` (empty) and
  `find <vendor> -type f -printf '%T@\n' | sort -n | head -1; ... | tail -1`
  (oldest == newest == the install second).
- `find` under a token-reducing proxy may prune dot-directories and hide the very files
  you are auditing. Use the raw `find` for any audit whose conclusion is "nothing changed".
