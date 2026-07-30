---
name: separate-setting-cap-from-model-cap
description: Use when a limit looks like a hard platform/version cap but a config file could explain it. Settles it with a within-version pair, a current-version counter-example, and a live probe matrix.
installer: auto-skill
created_at: 2026-07-27T04:22:41+00:00
created_session: 
trigger: complex-task
created_by: subagent:ceiling-synthesis
category: diagnostics
content_hash: 0d90b34f723ddf4064113f4e35439bc900542166abd902d13ca2d304e664c1fe
---
# Separate a "setting cap" from a "model/platform cap" with live probes

Use when a per-session limit (auto-compact window, context size, token budget) looks like a
hard platform/version cap, but a config file could also explain it. Transcript forensics alone
is CONFOUNDED — it cannot tell "the tool caps me" from "I capped myself". This settles it.

## Why the obvious analysis is not enough

Mining logs for "the limit always lands at X" proves only that X is the effective limit today.
Two hypotheses fit equally: (a) a config value you wrote, (b) a cap in the tool. Do not pick.
Run the three tests below; each one alone can refute one hypothesis.

## Test 1 — within-version pair (refutes "a version changed the cap")

Find two limit events in the SAME session/file recorded under the SAME tool version where the
limit differs. If the ceiling moved without a version change, no version cap exists.

```bash
# example shape: pull (timestamp, version, limitValue) triples out of structured logs
grep -o '"version":"[^"]*"' <log> | sort | uniq -c      # version timeline inside one file
```

## Test 2 — current-version counter-example (refutes "the installed version caps")

Find any session on the CURRENTLY installed version, with NO local override, that sailed past
the suspected cap with no limit event. One such session kills the version-cap theory.

## Test 3 — LIVE PROBE MATRIX (the decisive one)

Build a throwaway dir and ask the tool to print its own resolved limit under each combination.
Vary exactly one axis at a time: (i) the explicit flag value, (ii) the model/backend, (iii)
no-config-at-all. A read-only "show me your config" command is enough — do not run real work.

```bash
D=$(mktemp -d); cd "$D"; git init -q .              # some tools resolve config from the GIT ROOT
printf '{"<key>":<lowValue>}' > .claude/settings.local.json   # the suspected culprit file
<tool> --settings '{"<key>":<highValue>}' -p '<show-config-cmd>'   # flag vs file -> precedence
<tool> --model <smallModel> --settings '{"<key>":<highValue>}' -p '<show-config-cmd>'  # model clamp
<tool> --setting-sources=project -p '<show-config-cmd>'   # no user/local config -> built-in default
```

Read the three answers as a truth table:
- flag value honored over the file value  => the file was the cap. Not a platform cap.
- value silently reduced only for one model => a `min(modelMax, configured)` clamp. Per-model ceiling.
- no-config run shows a bigger number than your config => you were capping yourself.

## Rules

1. Probe the binary that is actually installed (`readlink -f $(which <tool>)`, `<tool> --version`).
   Analysis from logs of an older version is not evidence about today.
2. One axis per probe. A probe that changes model AND value proves nothing.
3. Check whether the limit is re-read live or snapshotted at process start — edit the file
   mid-session and re-ask. If snapshotted, every rollout step must include a restart.
4. Enumerate ALL writers of the value before recommending an edit:
   `grep -rn '<key>' <launcher-scripts> <wrappers> <skill-dirs>`. A launcher that passes the
   value as a CLI flag OUTRANKS every config file and will silently re-cap new processes.
5. Report the verdict as a truth table with the exact probe output, not as a conclusion.

## Anti-pattern

"Every observation lands at X, therefore X is a hard limit." That is the confound. If you did
not run a probe where the value was set to something OTHER than X, you have not tested anything.
