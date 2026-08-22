---
name: audit-handoff-contract-runtime-agnostic
description: 'Use when asked whether a different agent runtime could resume a workflow''s half-finished job: separate the on-disk state layer from the vendor supervision layer and prove portability with an…'
installer: auto-skill
created_at: 2026-08-22T11:32:32+07:00
created_session: 
trigger: 'complex-task'
created_by: 'subagent'
category: 'multi-agent'
content_hash: edcdf6b6e31e44912f2d9ab4caa00c027516b2765da7cc382e5c6a7043eef0e0
---
# Audit whether a multi-agent workflow's handoff is runtime-agnostic

Use when asked "could a different agent runtime pick up a half-finished job here?", or before
building a "central handoff layer" for a system that may already have one on disk.

## The mistake to avoid
Do NOT answer by reading the orchestrator prose and judging. Prose lies about itself: a step the
docs call a "gate" is often a sentence asking the LLM to run a check, which measurably never runs.
Separate **two layers** and audit them independently:
- **State layer** — the files that cross a task boundary (markers, ledgers, state files, docs).
- **Supervision layer** — liveness/turn-state/model/compaction/permission control wrapped around it.
A system is portable if the state layer is plain filesystem, even when the supervision layer is
100% vendor-locked. Report them as separate verdicts.

## Steps
1. Find the single source of truth for "what is a runtime artifact". Usually a gitignore-writer
   function or a cleanup list, e.g. `grep -n "_gi_marker_set\|gitignore" <engine>`. That list is
   your inventory — more complete than the one the requester handed you.
2. For each artifact, grep every site and classify WRITE / READ / DELETE:
   `for m in <markers>; do echo "== $m"; grep -n -- "$m" <engine> | cut -c1-200; done`
   Note which side writes it. Files the *supervisor* writes but calls "the worker's" are a common
   forgery hole (an existence-only gate on a file the supervisor authored gates nothing).
3. Assemble the brief/prompt path and quote it verbatim. Find the one line that concatenates the
   components (`grep -n 'cmd_.*brief\|> "\$bf"'`). Then check each component for a transcript read:
   `grep -nE "transcript|\.jsonl|session_id|conversation" <engine> | grep -v '^\s*[0-9]*:#'`.
   If none of the brief's components touch a transcript, the handoff is disk-only — say so with
   the line number, not "appears to be".
4. **Find an existence proof instead of arguing.** Look for a path already served by a different
   runtime: a 0-token/deterministic worker, a second implementation in another language, a CLI or
   extension that polls the same files. Grep for a function that *forges* the completion contract
   (`touch <done-marker>` outside the worker path) and for parity tests
   (`grep -rln "<marker>" --include=*.ts --include=*.py <other-repo>`). One working non-LLM
   consumer beats any amount of inspection.
5. Enumerate the vendor couplings that can BLOCK, separately from the ones that only degrade.
   Grep for hard-coded tool names, TUI glyph patterns, slash commands, hook JSON shapes:
   `grep -nE "'<ToolName>'|\"/[a-z]+ \"|stop_reason|end_turn|tool_use" <engine>`
   For each, check if there is an env off-switch. A coupling with an off-switch is a degradation;
   a coupling inside an irreversible action (merge/deploy) is the real blocker. Usually there are
   only one or two of the latter — name them exactly.
6. Check the resume-from-nothing doc against step 2's inventory. Flag artifacts that exist for
   resume but that the resume path never reads — a ledger nobody re-reads is the same amnesia the
   ledger was built to fix.
7. Check whether "memory/lessons survive" is enforced by code or by prose. `grep` the merge/land
   function's gate list. If the memory step is not in it, say the enforcement is zero, and name
   the compensating control (usually the supervisor writes its own stub deterministically).

## Verdict shape
"Portable for <path>, proven by <existing non-vendor consumer>. Not portable for <N gates>:
<name each, with file:line, whether it blocks, and its off-switch>." Never a bare yes/no.

## Gotchas
- A grep proxy/hook may truncate results silently (`[+N more]`). Use the raw command
  (`rtk proxy grep`, or the Grep tool) when a count matters.
- Huge single-file engines: read by `sed -n 'A,Bp'` around grep hits, never whole-file.
