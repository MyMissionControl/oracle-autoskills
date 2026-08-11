---
name: plan-gate-diagram-from-planning-docs
description: 'Use when auto-generating a diagram/summary into docs that must be right before code exists and stay fresh as the plan changes; fingerprint the derived model for drift.'
installer: auto-skill
created_at: 2026-08-11T12:05:41+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'docs-automation'
content_hash: 465c25b3048a63b9f180c0296e4aef3b35536e270ae5819f26e8ecd917f462df
---
# Generate a doc diagram/table from PLANNING docs, not code

Use when a pipeline auto-writes a diagram or summary block into project docs and it must be
**correct before the code exists** (a plan/design gate), and must stay correct when the plan
is edited later.

## Why not derive from code
A code scanner cannot run at the plan gate, so the doc is empty exactly when it is most
useful (the plan is still cheap to change). A mature design/spec doc usually already names
every endpoint, entity, store and external service — check before assuming you need code.

## Procedure
1. **Prove the source is parseable first.** Write a throwaway extractor against the REAL
   planning doc and print counts (entities, endpoints, components). Do not design the
   picture until the counts are right. Strip fenced code blocks before any inline-token scan
   — an embedded config/CSS block destroys backtick/keyword scanning.
2. **Bind components to declared facts, not to declared folders.** A folder/zone glob with
   zero bound facts is a *phantom*: plans routinely declare paths that never get built.
   Drawing only bound components removes them for free.
3. **Match identifiers on word boundaries** (`(?<![A-Za-z])tok(?![A-Za-z])`). A bare basename
   token matches inside longer words (`storage` inside `storagePath`) and silently wires
   every component to every helper with the same label.
4. **Scope a fact to the section that declares it.** Split prose on its own sibling separator
   and bind within one segment; a whole-section match attaches unrelated facts.
5. **Never emit an element with no relationship** — except an entry point, which must instead
   get an explicit edge from the actor. Otherwise adding a whole group of facts leaves the
   output unchanged and the drift check below goes silent.
6. **Assert before writing.** Refuse to write on: forbidden label characters, an unlabelled
   edge, unbalanced grouping, a duplicate output marker. Emitting nothing beats emitting a
   broken block.
7. **Non-latin truncation:** splitting on spaces cuts mid-word in scripts that do not use
   them. Back off to a safe break character, else drop the whole trailing run.

## Drift detection that actually fires
- Hash the **derived model** (sorted node+edge tuples), never the source bytes. A reworded
  sentence then rewrites nothing and the VCS stays clean; the hash moves only when the
  picture moves.
- Store it inside the generated block (`<!--<ns>:<name>-fp sha=… -->`). Its name must not
  contain the block marker string if any test counts marker occurrences.
- Report `unchanged` / `redrawn … delta=+N/-M added=… removed=…` on stderr.
- **Hook it at the irreversible action** (the call that dispatches work / deploys), not at a
  documentation step and never in prose. Replace any `grep -q <marker> || generate` existence
  guard: that guard means "written once, never refreshed". The generator self-guards via the
  fingerprint, so calling it unconditionally is cheap.
- Scaffold the output directory in the setup command, not in a prose instruction — otherwise
  every hook silently skips and the feature looks installed while doing nothing.

## Verify
- Old fixtures must stay green untouched: make the new path `rc 1` + a reason token, and let
  the caller fall back to the previous generator. Confirm any pre-existing failures also fail
  on a clean checkout before blaming your change.
- Test the drift path explicitly: run twice (assert unchanged AND that mtime did not move),
  then edit the plan and assert `redrawn` plus the named delta.
