---
name: thin-claude-md-index-for-baseline
description: Use when an agent re-explores a repo every session or you want to trim session baseline: add a thin auto-loaded CLAUDE.md map pointing to a heavy on-demand doc; verify paths before writing.
installer: auto-skill
created_at: 2026-07-24T04:11:30+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-opus-4-8
category: context-optimization
content_hash: a4c351995459b26c44443f3f4cacbda92b676b5c613d449d7c299a72de80d4cd
---
# Thin CLAUDE.md index to cut agent baseline + blind exploration

Use when an agent/oracle burns tokens re-exploring a repo or workspace every session, or you want to trim session baseline. The usual real problem is NOT baseline size — it is blind runtime exploration because nothing auto-loaded tells the agent where things are.

## Steps

1. **Diagnose what actually auto-loads at wake** (don't assume). Measure:
   - CLAUDE.md chain (project + `~/.claude/CLAUDE.md` + any `@import`)
   - Eager skill descriptions (`~/.claude/skills/*/SKILL.md` frontmatter) — these grow monotonically with auto-skill; a lazy-librarian MCP is the usual safety valve, don't hand-prune unless asked
   - MCP tool schemas — confirm they are **deferred** (huge if eager: N tools x ~200 tok)
   - SessionStart hooks — confirm they do NOT inject large context (many only record state)
   Baseline is usually fine; the leak is exploration.

2. **Look for an existing heavy overview doc** (PROJECT_CONTEXT.md / ARCHITECTURE.md / README / docs/). KEY TRAP: only `CLAUDE.md` auto-loads — a great overview doc that is NOT CLAUDE.md is invisible at wake, so the agent still explores blindly even though the map exists.

3. **Write a THIN `CLAUDE.md` at the repo/workspace root** = a map/index, not a dump:
   - key dirs + entry points, one-line role each, repo-root-relative paths in backticks
   - a "Where to start" section keyed to task type
   - a few fragile/surprising gotchas (stubbed subsystems, generated/gitignored dirs, non-obvious real engine location)
   - **POINT** to the heavy doc with specific section refs; do NOT duplicate it (progressive disclosure). Target ~400 tok. Trade: +~400 tok fixed baseline vs many-k blind `ls`/`find`/`grep` saved per navigating session.

4. **Write baseline prose in ENGLISH, not Thai/other non-Latin** — it tokenizes ~2x heavier while the agent understands English equally. Keep any human-facing reply-language rule as ONE line, placed once at the **workspace-root** CLAUDE.md — parent CLAUDE.md loads for all nested dirs, so one line covers every sub-repo.

5. **VERIFY before trusting/writing** (adversarial): `test -e` every referenced path, confirm each pointed doc exists and actually covers structure, read code to confirm role claims (e.g. "code lives in `<subdir>/`"). Fix errors first. If a CLAUDE.md already exists, do NOT clobber — merge or flag. For multiple repos, fan out investigate -> draft -> verify as a workflow pipeline.

6. **Do not commit** generated maps unless the repo is a designated tool repo and the human asks; leave untracked by default.

## Why
Auto-loaded prose is paid every session forever, so it must be a cheap index that earns its keep by killing repeated exploration — never a wall of detail. Measure, point, verify.
