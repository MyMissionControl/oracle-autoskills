---
name: adjudicate-count-on-live-corpus
description: 'Use when a document''s file/record count is disputed by a re-count: separate real error from time-drift via observer subtraction, per-tier breakdown, retention age-floor and orphan forensics.'
installer: auto-skill
created_at: 2026-08-06T08:39:01+07:00
created_session: 
trigger: 'complex-task'
created_by: 'subagent:count-adjudicator'
category: 'measurement'
content_hash: b200e8c50927136360aa1cd9233965ca2c7f2af0aae8263ccf1175ee3785f761
edited_at: 2026-08-06T08:45:52+07:00
edited_by: adjudication-subagent
---
# Adjudicating a disputed file/record count on a live, self-modifying corpus

Use when a document claims a corpus is N items, a verifier re-counts and gets M, and
you must say who is right. Typical corpora: agent/session transcript trees, log dirs,
cache dirs, queue dirs — anything the running tooling writes to while you measure.

**A count is not a fact. It is a measurement of a moving quantity at an instant.**
Before declaring anyone wrong, prove whether the population is stationary.

## Step 1 — Never trust "stable across repeated runs"

Two counters run seconds apart (e.g. `os.walk` and `find`) are NOT independent
evidence. They share the same time-point, so they can only confirm *precision*,
never *accuracy*. Drift over minutes/hours is invisible to them. Discard this
as evidence and measure drift directly.

## Step 2 — Subtract the observer

Your own investigation may be writing into the corpus. For agent transcript trees,
the workflow/session you are running inside creates files as it goes.

```bash
# find your own session/workflow id (often visible in your scratchpad path)
find <root> -type f -name '*.jsonl' -path '*<your_workflow_id>*' | wc -l
```

Subtract these before comparing to any earlier number. If the disputing parties ran
at different moments inside the same workflow, their delta is often *purely* this.

## Step 3 — Break the total into tiers, not one scalar

A single total hides offsetting moves (one tier grows, another shrinks). Count per
depth and compare tier by tier against the document's breakdown:

```bash
for d in $(seq 1 8); do
  printf "depth %s: " "$d"
  find <root> -mindepth $d -maxdepth $d -type f -name '<pat>' | wc -l
done
```

A tier that reconciles *exactly* once you add your own files proves the document's
scan was complete — i.e. it did not suffer a shallow-glob/missing-recursion bug.

## Step 4 — Test for a retention floor (the usual cause of shrinkage)

Corpora that only ever grow cannot shrink — unless something prunes them. Retention
usually deletes only the TOP-level record and orphans its children. Two tests:

```bash
# (a) age floor: oldest surviving item per tier
for d in <tiers>; do
  find <root> -mindepth $d -maxdepth $d -type f -name '<pat>' -printf '%TY-%Tm-%Td\n' \
    | sort | head -1
done
```

If the top tier has a hard floor (e.g. nothing older than exactly 30 days) while
deeper tiers reach much further back, retention is real and prunes only the top tier.

```bash
# (b) orphan forensics: child dirs whose parent record is gone
for dir in $(find <root> -mindepth 2 -maxdepth 2 -type d); do
  [ -f "${dir}.jsonl" ] || echo "orphan: $dir"
done | wc -l
```

Orphans are physical proof of deletion, surviving after the deleted record itself.

```bash
# (c) date the prune: deleting a file bumps its PARENT DIRECTORY's mtime
find <root> -type d -newermt '<doc date> 00:00' -printf '%TH:%TM:%TS %p\n' \
  | grep -v '<your_session_id>' | sort
```

Directories whose mtime is recent but whose surviving children are all old = a
deletion happened there. This gives the prune an exact timestamp. Check whether it
falls BETWEEN the document's measurement instant and the document's mtime — if so,
every reconstruction anchored at the document's mtime is already post-prune.

## Step 4b — Use BIRTH time (crtime), never mtime, to date arrivals

`-newermt` filters on mtime = *last append*. Live, still-being-written records
(the current session's own log) look "new" even though they predate the document,
and long-running records get misdated. `stat -c %W` gives true creation time on
ext4/xfs and cleanly separates "arrived after" from "existed before":

```bash
stat -c '%W %n' $(find <root> -name '<pat>') | awk -v t=<cutoff_epoch> '$1>t'
```

Then per tier: `now = born_before_cutoff + born_after_cutoff`. Any tier where
`born_after == 0` but `now < document_N` proves **deletion**, because nothing
arrived to mask it. That is a proof, not an inference.

Crucially, deleted files are invisible to any filter over the live tree. A
reconstruction like `find ... ! -newermt <doc_time>` counts *survivors*, so on a
pruned corpus it is a **lower bound**, never a snapshot. Never quote it as "what the
document should have seen".

## Step 5c — Cross-check a derived statistic, byte-exact

The strongest evidence that the document's instrument was sound is not the count but
a *derived* figure computed from the same scan — a median, a sum of sizes, a filtered
sub-population. Recompute it from today's survivors:

- If the derived figures reproduce **exactly** (to the byte) while only the count is
  short, the document counted correctly and the corpus lost items whose contribution
  to those figures was zero. A miscount cannot produce byte-exact agreement.
- Identify *which* bucket shrank. If the shrunken bucket is the one contributing
  nothing to the byte-exact total, that pins the deleted item's identity.

Beware the inverted accusation: a verifier seeing `1399 + 10 = 1409` versus a
document's `1399 + 11 = 1410` will call the document's 11 "inflated". Check the
other direction first — the 1399 matching exactly is the tell that the document was
right and one item of the 11 was deleted.

## Step 5 — Check boundary density for plausibility

Confirm the size of the loss is ordinary, not anomalous:

```bash
find <root> -mindepth <top> -maxdepth <top> -type f -name '<pat>' \
  -printf '%TY-%Tm-%Td\n' | sort | uniq -c | head
```

If ~20 items/day sit at the boundary, losing ~15 in one sweep is under a day's
churn — expected, not corruption.

## Step 5b — Sweep mtime cutoffs to find the instant that reproduces the document's number

Do not settle for "drift is plausible". Find the cutoff at which the corpus *equals*
the document's count. On a tier that only grows (never pruned), the match is exact
and settles the dispute outright.

```bash
for CUT in "<T-2>" "<T-1>" "<T>" "<T+1>" "now"; do
  printf "  %-18s -> %s\n" "$CUT" \
    "$(find <root> -mindepth <d> -maxdepth <d> -type f -name '<pat>' ! -newermt "$CUT" | wc -l)"
done
```

Caveats: `find -mindepth` counts one level deeper than a `relpath.count(os.sep)`
counter — align them before comparing tiers. Reconstruction is a *lower bound* on a
pruned tier (deleted items are invisible) but near-exact on an append-only tier whose
files are short-lived, so anchor the verdict on the unpruned tier.

Also check the document's own internal cross-references: a second figure elsewhere in
it (e.g. a filtered sub-population) that reconstructs exactly proves the author's
instrument was sound and shows which population each figure meant.

## Step 6 — Close the arithmetic explicitly

State one equation that explains *every* number in play:

```
document_N  -  pruned_since  +  your_own_files  =  your_count
```

If it closes exactly, the document was right at its time and the verifier merely
measured a different instant. If it does not close, you have a real discrepancy.

## Verdict rules

- Document right: its method was complete and the delta is fully explained by
  time-drift (pruning + observer additions).
- Verifier right: the document's tier breakdown fails to reconcile even after
  accounting for drift (e.g. it missed a whole tier — the shallow-glob bug).
- Both wrong: the corpus is non-stationary and neither carried an as-of timestamp;
  the honest answer is a number plus its measurement time.

## Reporting rule

Always report a count with **as-of time + method + what makes it move**. A bare
count on a live corpus is a claim with a hidden expiry date, and will be
"refuted" by the next person who runs the same command an hour later.
