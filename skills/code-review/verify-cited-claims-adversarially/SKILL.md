---
name: verify-cited-claims-adversarially
description: 'Use when asked to confirm/refute an audit''s claims that carry file:line citations: tell stale line-drift (check HEAD~1) from false claims, re-run cited greps, and probe stated conclusions instead of…'
installer: auto-skill
created_at: 2026-08-13T15:10:21+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'verifier-subagent'
category: 'code-review'
content_hash: 3f6f7ac32566b0cc7abf4974a2669060ed4395bc67a3a16099f175726dcda5c9
---
# Adversarially verify file:line claims (audit hand-off)

Use when handed a list of claims about a codebase with `file:line` citations (an audit
report, a review hand-off, another agent's findings) and asked to confirm or refute them.

## 1. Separate stale citations from false claims (do this FIRST)

A wrong line number is usually **drift**, not fabrication: the file grew after the claim
was written. Never rule "refuted" on a line mismatch alone.

```bash
cd <repo> && git log --oneline -3 -- <cited-file>     # what landed recently
git show HEAD~1:<path-in-repo> > /tmp/old.ts          # the state the claim was written against
cat -n /tmp/old.ts | sed -n '<cited-line>p'           # does the citation match THERE?
```
If it matches at HEAD~1, the claim is stale-cited but substantively checkable: verify the
substance at its NEW line in HEAD and report both numbers. Drift is systematic — one
inserted block shifts every later citation in that file by the same amount, so confirming
two or three anchors settles the whole file.

## 2. Re-run every cited command yourself

Cited greps are the most common failure: re-run the exact pattern and compare the hit
count. `grep -rn 'X *=' src/` "returns 0 hits" is refuted by 20 hits even when all 20 are
in `*.test.ts` — report the count AND the breakdown, so the surviving part of the claim is
not lost. Re-run case-insensitive and with a second tool when a claim rests on a zero-hit
result (a shell hook may rewrite grep/rg).

## 3. Probe conclusions, don't read them

Claims of the form "the code says X, therefore Y is impossible" are where real refutations
live. The prose in a comment is the author's assumption, not a measured property. Test Y:

- env/config precedence → run the real tool with both set and log which one fired
  (e.g. two wrapper scripts, one per source, each appending to a log file)
- "process would hang" / "cannot prompt" → reproduce with the same stdio and no
  controlling terminal (`setsid timeout 5 <cmd> < /dev/null`), and check whether the
  helper binary the tool falls back to is even installed
- "an ambient facility is absent" → print the env var that would expose it
- "the user sees message M on failure" → force the failure path and read what the
  error object actually carries (partial stderr often beats the generic message)

## 4. Verdict rule

Refute when **re-checking the cited evidence yields a different result** than stated:
wrong grep count, wrong runtime symptom, a conclusion the probe contradicts. Do not refute
for an off-by-N line number, an off-by-one count, or an over-broad word whose scope the
surrounding claims make obvious. Either way the note must state what survived, so a true
finding is never dropped along with its wrong sentence.
