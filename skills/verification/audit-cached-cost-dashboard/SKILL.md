---
name: audit-cached-cost-dashboard
description: 'Use when asked if a locally-computed cost/usage dashboard is right: re-implement its formula and diff per-file against its own cache to catch TZ-frozen buckets and divergent scanners.'
installer: auto-skill
created_at: 2026-08-10T14:40:20+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude-opus-5'
category: 'verification'
content_hash: e9441e83ad46222e93cc8782b17fb978010079d88723f0a6710d044bf78f3c7c
---
# Audit a locally-computed cost/usage dashboard against its own cache

Use when a tool computes money or counts from local log/transcript files and someone asks
"is this number right?" — especially when it keeps a persisted per-file cache.

## 1. Re-implement the formula, don't read it

Copy the pricing/aggregation function into a standalone script (node/python) that walks the
same source tree with the same rules (recursion depth, file glob, dedup key, skip conditions).
Reading the code only proves what it intends; re-running it proves what it produces.

## 2. Diff PER FILE against the app's own cache, not just the grand total

Totals hide offsetting errors. Load the app's persisted cache (`~/.cache/<app>/*.json`) and
compare each cached per-file aggregate to a fresh parse of that same file:

- cost matches on ~all files → the formula is correct; stop suspecting the math.
- a handful differ → check whether those source files grew after the cache timestamp.
- **bucket keys differ while costs match → a bucketing bug, not a pricing bug.** Go to step 3.

## 3. Classify mismatched buckets by re-deriving under each plausible assumption

For every mismatched entry, recompute its buckets under each candidate rule (local time vs
UTC, one code version vs another) and count how many entries match which rule. A clean split
("1666 match local, 159 match UTC") names the cause; a smear means something else.

**The trap this finds:** a per-file cache keyed only on mtime+size is ALSO implicitly keyed on
anything ambient the parse depended on — most often the **host timezone**, when day/hour keys
are rendered in local time. Change the machine's TZ (cloud VMs default to UTC until configured)
and every file not touched since keeps its old day boundaries forever. A version constant only
covers code changes. Confirm with `stat -c %y /etc/localtime` and compare it to the mtime range
of the mismatched entries.

Fix: store the ambient value (`Intl.DateTimeFormat().resolvedOptions().timeZone`) next to the
version in the cache file and require BOTH to match on load; bump the version once to purge.

## 4. Check the fields the formula ignores

Dump every key seen on the priced records and ask what the pricer doesn't read:
speed/tier/quality flags (premium modes are often a 2x rate), server-tool request counts
(billed separately), per-attempt iteration arrays, an empty/unknown model id. Quantify each
before reporting: "0 rows today, but silently 2x wrong if enabled" is a finding; guessing isn't.

## 5. Check date-scoped list prices

Rates are not constants. Introductory/promotional prices apply to usage **during a window**, so
the rate belongs to the record's own timestamp, not to now. Pass the timestamp into the pricer
and keep the rule permanently — deleting it after the window closes silently reprices history.

## 6. Cross-check every OTHER surface that shows the same number

Grep for all importers of the aggregator. A second, on-demand scanner for a detail/drill-down
view is a common source of divergence. Run both over the same real inputs and diff per entity:

- A dir/name pre-filter is the usual culprit. Log directories are named after the process's
  STARTING directory, while each record carries its own — so filtering dirs by an entity's path
  silently drops work done for it from elsewhere, and any `matches.length ? matches : all`
  fallback won't fire because the wrong-but-nonempty match wins.
- Prefer deriving the file list from the global cache (which already knows which files touched
  which entity), unioned with the name-matched dirs to cover files newer than the last scan.

## 7. Verify UI-layer filters too

Host-side numbers can be correct while the client drops rows: a "hide zero" filter plus an
entity that legitimately has no per-period data (restored from a durable ledger) makes a
feature that was explicitly built silently invisible. Extract the webview's inline script,
`node --check` it, then run it in a `vm` context with stub DOM objects and feed it a synthetic
row to prove the branch fires.

## Reporting

Rank findings by measured impact ("$2,158 = 34% of spend on the wrong day"), separate
"wrong now" from "latent", and state plainly what you verified as CORRECT — a bug hunt that
doesn't clear the parts that work leaves the user unsure what to trust.
