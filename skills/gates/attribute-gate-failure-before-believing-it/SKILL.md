---
name: attribute-gate-failure-before-believing-it
description: 'Use when a gate reports the same failure across early rounds of a staged build and it looks like the feature is broken — attribute it via reason-token precedence, artifact dates, and marker…'
installer: auto-skill
created_at: 2026-08-18T08:50:03+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude-opus-5'
category: 'gates'
content_hash: 21789dfcd8e9aaea04e18a410ff471a7e016722e12d25f233a091e7db3ffd3b7
---
# Attribute a repeating gate failure before believing it

Use when an automated gate (auth/login check, smoke, e2e, marker probe) reports the same failure in
several early rounds of a staged build, and the obvious reading is "the feature is broken". In staged
work the gate's **proof artifact** may not exist yet — the feature can be working while the proof is
structurally unavailable. Fixing the feature then wastes a round and hides the real defect: the
gate's wording.

## Steps

1. **Read the gate's reason-token precedence in its own source before trusting the message.**
   Most gates compute several conditions and report the *first* failing one, e.g.
   `<missing-input-still-present>` → `<bounced-back>` → `<marker-never-seen>`.
   Reaching the LAST token means every earlier condition already passed — often that is proof the
   action succeeded and only the *verification* failed. Grep the token strings in the engine:
   `grep -n '<token-a>\|<token-b>' <engine>` and read the ternary/case order.

2. **Date the artifacts, don't infer them.** For each file the proof depends on:
   `git log --diff-filter=A --format='%ad %s' --date=format:'%m-%d %H:%M' -1 -- <path>`
   Compare with the round boundaries (`git log --format='%ad %s' --grep='<round-commit-pattern>'`).
   This answers "what existed at capture time" with a timestamp instead of a guess.

3. **Ask whether the proof string can exist at all yet**: grep the declared marker/expected text
   across sources, excluding the docs that declare it — otherwise it matches its own spec file and
   the check always says "present".
   ⛔ Every `--exclude-dir`/`--include` must come BEFORE `--`; after `--` they are treated as
   filenames and the dirs are searched anyway (rc 0 for the wrong reason).
   `grep -rqF --exclude-dir=<docsdir> --exclude-dir=.git -- "$marker" "$root"`

4. **Check the plan/requirements for the round that owns it.** A tracker line like
   `R<n> — <requirement>  (round: <k>)` next to a manifest that already demands it at round 1 is
   the actual defect: two files hold both facts and nothing joins them.

5. **Fix the wording, never the verdict.** Split the honest state into its own token
   (`<action>-unverified` vs `<action>-failed`), keep the verdict conservative (still "not proven"),
   and print the real remedy: postpone the marker (comment it out) until the round that produces it.
   ⛔ Do NOT make the gate accept an unprovable marker — that reopens the class of bug where a gate
   declares success it never verified.

6. **Add a pre-flight so nobody needs eyes next time**: at the round boundary, when the declared
   marker text appears nowhere in sources, say so, name the consequence (which downstream gate gets
   skipped), and keep saying it every round until it can be satisfied.

## Verify

- negative control: marker present in a source file ⇒ pre-flight silent (a false warning trains
  people to ignore the whole gate)
- the genuinely-broken case still reports the old token (pin it in a test, or the split becomes a
  silent downgrade of a real failure)
