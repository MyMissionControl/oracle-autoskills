---
name: relocate-prose-gate-into-code-path
description: Use when a workflow's SKILL/prompt claims a gate the agent must run itself. Prove from transcript it never ran, re-derive the check, move into the irreversible-action function, TDD.
installer: auto-skill
created_at: 2026-08-01T01:53:00+07:00
created_session: 
trigger: reusable-workflow
created_by: claude-opus-5
category: workflow-hardening
content_hash: b34ffa6b93137546294b0fcc1c3a38b58e53382bcd61d9363bacac7712739d7b
---
# Relocate a prose gate into the code path

A "gate" written as instructions for an agent to run (SKILL/AGENTS/prompt prose) is a gate that can be
skipped silently. Move it into the one code path that cannot be bypassed. Use this when auditing any
agent-driven workflow that claims to enforce something.

## 1. Prove the gate never ran (do this first — don't trust the prose)

```bash
# a) is it advertised as mechanical?
grep -rn "GUARD\|gate\|must\|ต้อง" <skill-or-prompt-file> | head
# b) did it EVER execute? search the agent's own transcript, not the docs
grep -c "<a literal string only that gate prints>" ~/.claude/projects/*/<session>.jsonl
grep -c "<the verb/command the prose tells the agent to run>" <transcript>
```
0 hits across a full multi-step run = the gate is decorative. Record the denominator
("0 of N tool calls over M sprints") — that number is what makes the case.

## 2. Re-derive the check yourself — the prose formula is often ALSO wrong

Prose gates are rarely tested, so they carry latent logic bugs. Before porting, ask for each
condition: *what OTHER state produces this same reading?* Classic shape:

- a counter that is 0 both when "nothing was done" and when "the work already landed"
- worse: the innocent case makes an earlier short-circuit fire, so the gate is never reached at all

Fix by adding the one stored fact that separates them (a base/start marker written at the moment
work was handed out), not by reordering the checks.

## 3. Find the chokepoint

The gate belongs in the function that performs the irreversible act (merge / deploy / publish),
placed **before every side effect** — before fetch/push/PR creation, and before any early
`return` for a mode/short-circuit, so all modes are covered.

## 4. TDD, and expect neighbours to go red

```
RED   test asserting the gate BLOCKS (assert the verdict AND that no side effect happened:
      no PR created, nothing pushed — inspect a command shim log, not just the return value)
RED   control test: the resume/legitimate case must NOT be blocked, plus an assertion proving
      that case is genuinely indistinguishable by the OLD formula (else the test passes for free)
GREEN implement; return a distinct verdict string per cause, and a non-blocking
      SKIP:<why> (loud on stderr) when the gate cannot measure — never a silent pass
```
Neighbour tests that never created the required artifact will now fail. Decide per test:
did it *deliberately* assert the fail-open (a comment saying "existing behavior"), or did the
fixture just not bother? Incidental → fix the fixture. Deliberate → say in the commit message
that you are overturning it, and why.

## 5. Commit discipline

- New verb / new file → its own commit, additive, old paths unaffected.
- Change to an existing verb → **one commit per verb, with its own test**; a feature marker cannot
  gate a behavior change inside an existing call path, so the commit is the unit of revert.
- Then shrink the prose: delete the inline block, keep one imperative line pointing at the verb,
  and move the incident history into the code comment. Verify the doc's size guard still passes
  BEFORE committing — a fix that documents itself past a byte ceiling turns the suite red.

## Anti-patterns

- Porting the prose formula verbatim (step 2 exists because it is usually broken).
- One verdict for causes with different remedies — if the fix is "author A writes the file" vs
  "author B fixes the code", they must be different strings, or the message tells the wrong party.
- Blocking when the gate has no data (old runs) — that turns an audit into an outage. SKIP loudly.
