---
name: test-deprecation-warning-deadline
description: 'Use when a claim treats a tool''s ''will stop working in the next major'' warning as a dated forward-compat liability: check if that major already shipped, bisect the real introduction version, strip…'
installer: auto-skill
created_at: 2026-09-01T18:45:31+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'adversarial-verifier'
category: 'tooling'
content_hash: d1cd4a8999d9f02c25656c4d177eaabb04952af38b140bc78542a4f00530621b
---
# Test a deprecation warning's own deadline before calling it a liability

Use when a claim says "tool X warns this will stop working in the next major" and treats that
as a dated forward-compat risk. The warning text is evidence of a warning, never evidence of a
deadline. Three checks turn the claim into a fact.

## 1. Is the "next major" already published? (usually yes)

Do NOT assume the threatened major is hypothetical. Check the registry first:

    npm view <pkg> dist-tags --json
    npm view <pkg> versions --json | tr -d ' "[],' | grep '^<N+1>\.'

If it exists, install it to a throwaway prefix and run the real command:

    mkdir -p $W/pfx && npm install --prefix $W/pfx --no-save --no-audit --no-fund <pkg>@<N+1>
    node $W/pfx/node_modules/<pkg>/bin/<cli>.js <verb>   # run the bin directly

If the next major still only warns (rc 0) and still prints the SAME "next major" sentence, the
message is rolling boilerplate from a generic unknown-key handler, not a dated deadline. Say so.

## 2. Find the exact version that introduced the warning

A claim of the form "vN warns" is often really "vN.M+ warns". Sweep oldest-first with a cheap
read-only verb, and count the specific string, not any warning:

    for V in <list>; do
      n=$(npx --yes <pkg>@$V <cheap-verb> 2>&1 | grep -c '<exact warning substring>')
      echo "$V -> $n"
    done

Then bisect the minor. A wrong boundary is the difference between "the major changed" and
"a patch release changed".

## 3. Strip the harness out of the measurement

`npx --yes <pkg>@N <verb>` runs the OUTER tool first, which may export config into the child's
environment and produce a phantom EXTRA warning the real deployment never sees. For npm the
outer one exports `npm_config_<key>` from the project config file, yielding both an
"Unknown env config" and an "Unknown project config" line where production emits only one.

Re-run with the harness removed and a clean env before quoting the output:

    env -i HOME=$HOME PATH=$PATH node $W/pfx/node_modules/<pkg>/bin/<cli>.js <verb>

Compare line counts. Report only the lines that survive.

## 4. Before recommending the "modern" replacement, run it on the INSTALLED version

The suggested migration is usually documented for a newer major of the *other* tool than the
one on the box. Test all three arms with a probe that observes the actual EFFECT, not rc:

  A. current config file          -> expect effect present
  B. new config file, new key     -> ?
  C. no config at all             -> control, effect absent

Two silent failure shapes to expect from arm B, both of which rc alone hides:
  - the new file exists but the key is IGNORED -> rc 0 and the effect silently reverts to C
  - the new file is structurally invalid for that version -> non-zero rc with ZERO bytes on
    both stdout and stderr

Always assert the effect directly (a file/symlink/tree the setting controls), never rc, and
never the tool's own log line.

## Reporting

Separate the reproduced measurement from the interpretation. It is normal for the numbers to
reproduce exactly while the "therefore this is a liability" clause is false. Confirm the first,
refute the second, and name the installed version that makes it moot today.
