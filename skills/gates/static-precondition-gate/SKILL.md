---
name: static-precondition-gate
description: 'Use when an expensive build/verify gate caught a defect only after a full install+build and reported an unreadable stack trace — turn it into a millisecond static rule over declaration files, with 0…'
installer: auto-skill
created_at: 2026-08-16T16:01:34+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'gates'
content_hash: 16a616829c23fd2c8ab3de21671b253ce1f4eee34f09bcfbf17b43bf37a01f0f
---
# Turn an expensive gate's failure into a cheap static rule

Use when a build/verify gate **did** catch a defect, but only after paying the expensive path
(full install + build, a boot, a network round-trip), and the failure it reported was a
downstream stack trace that never named the fix. The goal is not to replace the expensive
gate — it stays — but to add a rule that reaches the same verdict from **declaration files
only**, in milliseconds, and says what to change.

The tell: you can state the failure as a rule over two files ("declares X but nothing does Y")
without running anything.

## Steps

1. **Write the rule as one sentence over declarations.** Name the two files (a manifest +
   a config/schema) and the missing link between them. If you cannot, this is not the pattern —
   stop.
2. **Get ground truth first.** Run the fact query across **every** real instance you have, not
   just the failing one, and write down the expected verdict per instance. This is the only
   defence against a rule that fires on healthy projects.
   ```bash
   for p in <instances>/*/; do printf '%-30s ' "${p%/}"; <extract the two facts>; done
   ```
3. **Tests before code.** Add to the existing suite for that gate, one assertion per grade,
   plus the pair every honest gate needs: **"fires on the broken shape"** and **"goes silent
   once the documented fix is applied"**. Run them and watch them fail for the right reason.
4. **Four grades, never two.** `OK` · `WARN` (still broken for a cold consumer, but a named
   escape hatch exists) · `FAIL` (cannot possibly work) · `NOT_SCANNED` (this rule does not
   apply here). ⛔ "did not check" must never share wording with "checked and passed" —
   a report that says OK for an unscanned project is worse than no report.
5. **Every accepted mitigation must silence it.** List them explicitly (the artifact is
   committed · a lifecycle hook already runs it · the tool generates it itself). A rule that
   stays red after a legitimate fix trains people to ignore the whole gate.
6. **The message carries the fix, not the symptom.** One line: what is declared, what is
   missing, what breaks, and the exact edit to make.
7. **Re-run step 2's loop against the finished rule** and report `<n> flagged / <total>` with
   the false-positive count. If it is not 0, fix the rule, not the projects.
8. **Register the check's name wherever results are tabulated.** Report tables usually iterate
   a hardcoded gate list; a new check missing from it renders as `-` forever, which those
   tables normally mean "this gate did not exist yet". Grep for the list before you finish.
9. **Hang it where it fires early.** The expensive gate usually runs once at the end. The
   static rule costs nothing, so also call it at each iteration/sprint boundary — but suppress
   it where the full report already prints it, or readers count one defect twice.

## Guards

- ⛔ Do not delete or weaken the expensive gate. The static rule is a **faster, clearer path to
  the same verdict**, not a replacement — it only knows what the declarations say.
- ⛔ Do not fix the instances you found. They are evidence; the rule is the deliverable.
- ⛔ Regression sweep: any suite that counts the gate's output lines will now be off by one.
  `grep -l` the test dir for the gate's name and run those suites.
