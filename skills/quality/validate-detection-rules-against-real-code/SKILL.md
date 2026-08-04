---
name: validate-detection-rules-against-real-code
description: Use when adding grep/AST rules to a linter, scanner, or CI gate. Validate against a hand-audited real codebase before trusting your own fixtures; ship report-only first.
installer: auto-skill
created_at: 2026-08-04T13:59:13+07:00
created_session: 
trigger: reusable-workflow
created_by: claude
category: quality
content_hash: b1c0da2a02f70b950f35fe037f4638fdcb8cea1b7b42587f94f78ff1406634a2
---
# Validate detection rules against real code, not just your own tests

Use when adding grep/AST-based rules to a linter, security scanner, or CI gate. Your own
fixtures will pass — they were written from the same mental model as the rule. Only real
code exposes a wrong mitigation pattern or a wrong scope.

## Procedure

1. **Write the rule with an explicit mitigation.** Every rule = trigger + "accepted fix".
   Fixing the finding must silence it, or people disable the whole gate.

2. **Write paired tests: fires / silenced.** For each rule, one fixture that triggers and one
   with the mitigation applied. Necessary, not sufficient — go to step 3.

3. **Run it against a real codebase you have already audited by hand.** Pick a repo where you
   know the true findings. Compare rule output to your hand list:
   - findings you found but the rule missed = **false negative** — usually the mitigation
     pattern is too broad and matches unrelated code
   - findings the rule reports that are not real = false positive — tighten the scope
   Run over **all** files, not only the ones you suspect, or you never measure FP rate.

4. **Fix the regexes, then add a regression test for each miss** with a comment naming the
   real line that fooled it. This is the test your fixtures could not have produced.

5. **Report "not scanned" separately from "clean".** If no file matched the rule's language or
   scope, say so. Reusing the success word for "did not look" reads as a pass and is the
   failure mode that survives longest.

6. **Ship report-only first.** Emit findings without blocking; promote to blocking only after
   the FP rate is measured on real code. A gate that blocks on noise gets switched off entirely,
   taking the true positives with it.

7. **Put the summary where the decision happens.** Writing details to a log file is not enough —
   on a passing run nobody opens the log. Echo a one-line count to the stream the caller
   already reads.

## Traps

- Mitigation patterns like `\.length >`, `size >`, `if (max` match ordinary code. Prefer names
  that only appear when someone deliberately capped something (`MAX_`, `maxEntries`, `maxSize`).
- Scope findings to the code the current author actually changed (in git: the author's own
  commits, first-parent, no merges). Scanning the whole tree blames the wrong person and
  buries new findings in old ones.
- Exclude test files: they deliberately contain the dangerous shapes you are hunting.
