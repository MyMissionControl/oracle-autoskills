---
name: thin-hot-context-file
description: Use when thinning a large always-loaded skill/context file (SKILL.md, CLAUDE.md) to cut per-turn tokens safely: audit mass, move cold/opt-in blocks to references/, TDD byte-ceiling guard.
installer: auto-skill
created_at: 2026-07-29T15:22:13+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: refactor
content_hash: 55c614221e2b52b177e87f0bd7d53143800fb70b33fa6cd4fc78439710d1543f
---
# Safely thin a large always-loaded context file (SKILL.md / CLAUDE.md / big .md)

Goal: cut per-turn tokens on a file that loads WHOLE into an agent's context EVERY turn, WITHOUT changing behavior. The fat is usually a minority; much "prose" is load-bearing guidance. Cut only what's provably safe; report the honest floor (don't chase a target number into hot content).

## 1. Isolate + baseline
- If the file is symlinked LIVE (editing it deploys to running sessions), work in an isolated git worktree off main — never edit the live working tree.
- Run the existing test suite once = clean baseline. Record any pre-existing/env failures so later you can prove "no NEW failures", not "all green".
- Grep the tests for the file's name: tests that pin its content are hard constraints on what you may move/delete (e.g. a heading a test asserts stays).

## 2. Audit where the mass is (data first, before cutting)
- Per-section size: awk '/^#{1,3} /{if(h)printf "%7d  %s\n",c,h;h=$0;c=length($0)+1;next}{c+=length($0)+1}END{if(h)printf "%7d  %s\n",c,h}' FILE
- Classify each heavy section HOT vs COLD:
  - HOT = executed code, the exact strings sent to other agents, routing/step-order, and guidance-comments that steer behavior ("don't re-run X", "send Enter separately"). OFF-LIMITS.
  - COLD = opt-in/default-OFF/rare blocks, a recap/index that duplicates inline rules, historical WHY-essays, dates, provenance notes.

## 3. Safe cuts only
- Compress a recap/index that duplicates rules stated inline elsewhere -> one terse line per invariant (keep it as an index; keep the heading if a test pins it).
- Move OPT-IN / default-OFF / rare blocks to a references/ file + leave a 1-line pointer stating the trigger condition ("if <marker> -> cat references/<x>.md, else skip"). Default runs then pay 0 extra cat and save the bytes every turn.
- Trim historical/date/provenance WHY-essays down to the imperative rule (keep every hard ⛔/guard).
- Never trim executed code or agent-facing strings. If reaching a target number would require touching HOT content, STOP and report the honest floor — correctness beats the number.

## 4. TDD guard test — RED first
Write a permanent guard test asserting THREE things; run it and watch it FAIL before cutting:
- anti-bloat: wc -c byte ceiling (use bytes, NOT wc -m — locale-safe for multibyte/Thai).
- moved-out: each references/ file exists + contains a sentinel; the main file has the pointer; the moved bulk sentinel is GONE from the main file.
- anti-over-cut: hot tokens (key verb names, step numbers, executed-branch labels, the core rule) are STILL present inline.

## 5. Apply cuts — splice by line-number for fragile multibyte blocks
Literal find/replace on Thai/multibyte blocks fails on ambiguous empty-quote lines (">" vs "> ") and invisible whitespace. Instead:
- Write each NEW (short) block to a plain temp file (no shell/tool escaping headaches).
- Tiny python reads the file's lines, replaces (start,end) 1-indexed ranges with each new block, applying ranges in DESCENDING start order so earlier indices don't shift. Zero transcription risk on the OLD content (you only supply line numbers + new text).

## 6. GREEN + land + honest caveat
- New guard test GREEN + full suite == baseline (same pre-existing fails, zero new) + code-fence count even + no orphaned heredoc terminators.
- Stage by explicit path, git diff --cached to confirm only intended files, commit, ff-merge to main (deploys via symlink), remove worktree + branch.
- Flag what a unit test CANNOT verify (e.g. "does the agent now cat references more often per real run?") as a live-verify caveat, and offer to revert the moves if that regresses.
