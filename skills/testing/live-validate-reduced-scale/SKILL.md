---
name: live-validate-reduced-scale
description: Use when a spec item needs live validation at a scale too costly to run: run the real app on throwaway infra with thresholds lowered.
installer: auto-skill
created_at: 2026-07-29T16:12:53+00:00
created_session: 
trigger: reusable-workflow
created_by: opus5-main
category: testing
content_hash: 9fa871afe6e43109a5d38660d4a748fa2a42367082299a91f61c9341f937e678
---
# Close a "needs live validation" item by running the real thing at reduced scale

Use when a rollout/spec item says a feature must be proven against the REAL application
(not a mock) at production scale — a long build, a big dataset, hours of runtime — and
paying that scale is impractical right now. Mocks cannot close these items because the
whole risk is "how does the real app actually behave". Reduced scale can.

## The move

Run the REAL application, on throwaway infrastructure, with the feature's own thresholds
turned down so the identical code path fires cheaply.

1. **Isolate the blast radius.** Throwaway working dir, throwaway socket/port/namespace,
   and a hard guard that aborts if you see anything you did not create. For tmux
   specifically see the isolated-socket procedure skill.
2. **Launch through the real launch path**, not a hand-written command. If a bug in that
   path is what you are validating, hand-rolling the invocation validates nothing:
   `CMD="$(<tool> print-launch-cmd <args>)"` then run `$CMD`. Assert the flag you care
   about is present in `$CMD` before you even start it.
3. **Pick the cheapest real backend.** For an LLM app that means the cheapest model —
   and pick one DIFFERENT from the default, so "it used the right one" is unambiguous
   rather than accidentally correct.
4. **Turn the threshold down instead of building the scale up.** `FLOOR=15000` instead of
   the production `140000`; `MIN_ROWS=3` instead of `100000`. Same branch, same code, ~1%
   of the cost. State in the write-up that the floor was lowered and why that keeps it valid.
5. **Verify from the application's OWN artifacts**, never from your tool's return string.
   Its log/transcript/metadata is ground truth; your own "SENT ok" is not evidence.
   `<tool> print-launch-cmd` said the right thing AND the app's own record agrees = proven.
6. **Drive the failure branch too, in the same run.** Cheap once the harness exists, and it
   is where the finding usually is.
7. **Name the residual gap explicitly.** Reduced scale proves the mechanism; it does not
   prove the *call site* fires at the right moment inside the real orchestration. Write
   that sentence down rather than marking the item unconditionally done.

## Why bother (what this catches)

Real apps gate on things your model of them does not. A concrete instance: a compaction
command was assumed to trigger on token count; the real app gated on MESSAGE COUNT, so a
session holding 72k tokens in one pasted message was refused outright. The tool then waited
out its entire verify budget and reported `unverified:timeout` — indistinguishable from
"unknown" when the truth was "refused, nothing to do". Only a real instance shows this.

The generalizable lesson: **when the real app refuses, that is a distinct outcome from
"failed" and from "unknown".** Detect the refusal text and report it as its own state, or
you will burn a full timeout and then mislead the reader.

## Turning the run into a permanent test

Fold the discovered branch back into the mock-level suite (fake just the signal the code
reads — the refusal line — and assert both the verdict AND that it returns fast, e.g.
`elapsed < 12s` against a 30s budget). Keep the expensive real-app harness as a scratch
script; keep the cheap assertion in the suite.
