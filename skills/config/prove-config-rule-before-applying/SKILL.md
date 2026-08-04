---
name: prove-config-rule-before-applying
description: Use when adding a harness config rule (permission deny/allow, feature override) whose target you cannot observe directly — prove the syntax with a control test before writing the real config.
installer: auto-skill
created_at: 2026-08-04T09:03:28+07:00
created_session: 
trigger: error-recovery
created_by: claude-opus-5
category: config
content_hash: a84de052d703ce182fb077dc48eca17e156323e0369aba2e7f5891f154187cb0
---
# Prove a settings/config rule takes effect before applying it

TRIGGER: you want to add a rule to an agent-harness config (permission deny/allow,
feature override, skill gate) and you cannot directly observe the target, because the
thing you want to block is not registered in an ordinary session, or only appears in
some contexts.

## Why the obvious probes fail

Test these first and expect them to tell you nothing:

- `<cli> --version` (or any subcommand that doesn't start a session) usually does NOT
  validate the config file — an invalid rule passes silently.
- Writing a deliberately bogus value and looking for a warning: many harnesses accept
  unknown enum values silently, so "no error" is NOT evidence the value is valid.
- Grepping a bundled binary for the enum: works but is slow on a 200MB+ single-file
  bundle and easily gets interrupted. Only use it to find the *reason strings*
  (e.g. `"<X> blocked by permission rules"`), which you then match against later.

## The procedure that works: control test, then transfer

1. Pick a **control** — something in the same rule family that you CAN observe in a
   plain session (an installed skill, a common tool, a subcommand you can invoke).
2. Write the rule for the control into a THROWAWAY config file, never the real one.
   Most CLIs take `--settings <file>` / `--config <file>` for exactly this.
3. Run one minimal headless call that forces the control to be exercised, and phrase
   the prompt so the answer is the tool's own output, not the model's summary:
   "Call <tool> with <args> right now. Report VERBATIM what the tool returned, one line."
   Use the cheapest model available.
4. Assert on the harness's own refusal string — ideally the one you found in the
   bundle. A paraphrase from the model is not proof.
5. Run the negative control too: same call WITHOUT the rule must succeed. Without this
   you cannot tell "blocked" from "was never going to run".
6. Only now merge the same rule shape for the real target into the real config:
   read -> merge into the existing array -> write -> re-read and print the whole
   structure to prove nothing else was dropped. Keep a backup until verified.

## What to report

State plainly which half is proven and which is not:
- "syntax proven" — the control test passed both ways.
- "effect on the real target unverified" — say why (target not registered in a plain
  session) and name the observable that will settle it on the next real run.

Never report an unverified config change as done. A rule that silently does not match
is exactly the failure class you were trying to fix.

## Also worth knowing

- Config arrays MUST be merged, never replaced — dump key counts before/after
  (`allow=848`, `14 top-level keys`) as the receipt.
- If a rule needs to reach a process the harness spawns (not your shell), a shell
  `export` will not get there. Put it in the harness config's env block: a
  session/server that already exists inherits its OWN environment, not your shell's.
  Verify by reading `/proc/<child-pid>/environ` of a process the harness spawned —
  the parent CLI often lacks the var while its children have it, and the children are
  what matter.
