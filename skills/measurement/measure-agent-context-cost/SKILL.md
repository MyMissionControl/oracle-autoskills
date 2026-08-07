---
name: measure-agent-context-cost
description: 'Use when auditing per-request token spend from agent session transcripts: accumulate model plus the 3 traps (base64 images, unsent hook records, deferred tool schemas) that inflate it 16-35x.'
installer: auto-skill
created_at: 2026-08-07T16:17:57+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude'
category: 'measurement'
content_hash: 2ef92b85502593c95a468b6247e7c35e4551eb6916953bf75090b0c45b8ca07f
edited_at: 2026-08-07T16:47:31+07:00
edited_by: skills-mcp
---
# Measure per-request context cost from agent transcripts

Use when asked where an agent's token spend actually goes, and the evidence is a
corpus of session transcripts (`.jsonl` records with a per-message `usage` block).
A naive `chars/4` sweep will hand you three large, confident, wrong numbers — each
one pointing at a lever that does not exist. Check all three before recommending
any action.

## Model

**Context cost accumulates.** A block injected at turn 5 is re-sent at turns
6, 7, 8... so its cost is its size times the remaining requests in that session.
Walk each transcript in order with a running per-category counter, and at every
billed request add the *current* counter into the totals. Divide by total billed
requests at the end.

- Clear the counter on a compaction boundary (`isCompactSummary`, or a
  `compact_boundary` subtype) — compaction is what stops the accumulation.
- Keep sub-agent / sidechain records (`isSidechain`) in a **separate** accumulator.
  They live in the parent's file but form their own context; folding them in can
  push your content total past 100% of billed input.
- A one-time `Counter` of bytes per category is **not** comparable to an
  accumulate-model total. Use one-time sums for *shares within a category* only.

**Report in effective tokens, not nominal.** Weight by the price ratios
(`input x1 + cache_write x1.25 + cache_read x0.1 + output x5`) using the corpus's
measured cache-hit rate. A prefix at a 95%+ hit rate costs roughly a tenth of its
nominal size, which reorders the table.

## Before any of that: get the corpus selection right

The traps below inflate a *per-request* number. These three inflate the **set of
records you count at all**, so they scale everything downstream and are invisible
in the output — the totals just come out large and plausible.

**Window the records, not the files.** `if os.stat(p).st_mtime < CUT: continue`
selects sessions *touched* inside the window and then sums **every record in
them**, including history from far outside it. One long-lived pane leaks its whole
life into a "last N days" total. Measured on a real 21-day audit: records from
**54 days back** were still being counted; the headline area was **1.93B / 34% of
usage when the truth was 1.00B / 21%** — off by 2x. Keep the mtime check as a cheap
pre-filter and add the real one per record:

```python
if str(d.get("timestamp"))[:10] < CUTDAY: continue   # the actual window
```

The bias is not uniform. It concentrates on exactly the long-running sessions an
audit is most likely to be *about*, so the worst-inflated row is usually the one
the audit is recommending action on.

**Dedupe by message id.** One transcript record is written per content block, and
every record of the same assistant message repeats the *same* `usage` object.
Counting usage-bearing records overstates by ~2x (measured: 2.3x). Key on
`message.id`, falling back to `requestId`.

**Decide once whether a "count" means blocks or requests, and say which.** A turn
that calls `Read` three times is one request and three `tool_use` blocks. Both are
legitimate; mixing them in one table is not. Also, summing per-tool request counts
across tools **double-counts** any request that used two of them — if you want
distinct requests, take a set union, do not add the columns.

**Sanity check that survives all three:** ratios are far more robust than
absolutes here. When a re-measurement disagrees with an earlier audit, expect the
shares (x% of requests do Y) to reproduce and the absolutes to be the thing that
moved — and check the window before you check the arithmetic.

## The three traps

**1. Images are not `chars/4`.** Base64 payload length has nothing to do with
vision tokens. Decode the header, read the real dimensions, and apply the
provider's formula (for Anthropic: downscale so the longest edge <= 1568, then
`w*h/750`, capped ~1600). Measured miss: **35x overstatement** — a screenshot read
as 38,000 tokens actually costs ~1,100.

**2. Not every record in the transcript is sent to the model.** Transcripts are
local bookkeeping as well as conversation. Hook-result records in particular can
be recorded with an empty body and dropped before the message list is built. Check
by (a) counting how many of those records have an empty content field, and (b)
grepping the agent binary for the type name to find the push guard. Measured miss:
a whole category costed at 561 eff/req that is **never sent at all**.

**3. Tool schemas may be deferred.** If the harness lazy-loads tool definitions,
the always-on prefix carries tool *names* and the schemas arrive on demand. Costing
the schema JSON then overstates by the ratio between them. Look for a
`deferred_tools`-style attachment listing bare names, and check whether it appears
across the whole measured window, not just recently. Measured miss: **16x**, and it
made "trim the unused tools" a dead lever — the platform had already pulled it.

## Stop estimating the prefix — probe it

Everything above estimates from transcript bytes. The always-on prefix can be
**measured exactly**, and it is deterministic, so do that instead of dividing
characters by four.

Run a throwaway headless session with a pinned session id, then read the first
billed request out of its own transcript:

```sh
SID=$(python3 -c "import uuid;print(uuid.uuid4())")
cd <the real project dir>            # prefix includes project-level config
timeout 900 <agent-cli> -p "Reply with exactly: OK" --session-id "$SID" </dev/null
# then read <transcript-dir>/$SID.jsonl, first assistant record with usage,
# and sum input + cache_creation + cache_read
```

- **Pin the session id.** Globbing for "the newest transcript" finds your own live
  session, which is being appended to continuously, and silently reports its
  first request instead of the probe's.
- **Redirect stdin from /dev/null**, or the CLI stalls waiting for piped input.
- **Use the same model the real sessions use.** A listing budget computed as
  `fraction x context_window` demotes entries on a smaller-window model, so a
  cheap fast model measures a different prefix than the one you care about.
- Run the baseline **twice**. In practice it repeats to the token; if the two
  disagree, you have found noise and must bound it before trusting any delta.

**Measure ceilings before realistic versions.** Replace the whole component with a
stub (empty the index file, set every entry to suppressed) and probe. That gives
the maximum the lever can ever return, in one run, with no editorial judgement.
Only if the ceiling clears your bar is it worth designing the careful version.

**Check the lever is linear.** Probe at full, half, and empty. If tokens-per-char
is constant across all three, one measurement predicts every trim size. This also
exposes real density: markdown indexes full of hyphenated slugs measured **2.07
chars/token**, not 4 — so `chars/4` *understated* that file by 1.9x while
simultaneously *overstating* base64 images by 35x. The naive divisor is wrong in
both directions at once.

**Restore from a byte-level backup and prove it.** Copy the originals aside first,
`diff -q` every touched file at the end, and print the result. A probe suite that
leaves a config half-swapped is worse than no measurement.

## Procedure

1. **Pre-register the decision rule before looking at any number.** e.g. `>= N
   eff tok/req AND has a lever that does not remove capability AND reversible ->
   act; below that -> record only`. Writing it afterwards is how a 286 becomes
   "close enough to 500".
2. Build the accumulate model above; print nominal and effective side by side,
   plus each category's share of measured billed input.
3. Run the three trap checks against your top three rows specifically. The traps
   all inflate, so they cluster at the top of the table — which is exactly where
   they do the most damage to a recommendation.
4. State the unexplained residual out loud. Content will not sum to billed input
   (system prompt, tool schemas, and injected reminders are not in the records).
   Report the gap as a gap; do not scale numbers up to close it.
5. Apply the rule mechanically. If nothing clears the bar, the deliverable is the
   corrected table plus "nothing changed, here is why" — that is a result, not a
   failure to deliver.

## Rule of thumb

Every trap here inflated the estimate, and each one pointed at an appealing,
easy-sounding fix. Treat a large number in this kind of audit as a hypothesis with
one cheap disproof available, and go find the disproof before proposing the work.
