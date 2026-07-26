---
name: mc-orches-dev-verify
description: How to dev+verify changes across the MissionControl extension (TS/bun) and the orches-drive skill (bash), incl cross-repo contract round-trip
installer: auto-skill
created_at: 2026-07-13T02:37:15+00:00
created_session: 
trigger: reusable-workflow
created_by: claude
category: missioncontrol
content_hash: c905eef6cd67e7b86a8572b028aeb1d218f342978fe252dd8c5860eb8e7a12ce
---
# MissionControl extension ↔ orches-drive: dev & verify

Dual-repo. Extension = `soulbrew/github.com/fufu-2345/missionControl/extension` (TS).
Skill = `orches-skills/skills/orches-drive` (bash), symlinked to `~/.claude/skills/orches-drive` (edits hit LIVE drives — additive only, dummy-test first).

## Run tests / build (there is NO npm "test" script)
- Pure-fn unit tests: `cd extension && bun test [src/commands/foo.test.ts]` (bun:test)
- Type-check glue: `npm run compile` (tsc -p ./ → out/) — must exit 0
- orches-drive bash tests: `bash ~/.claude/skills/orches-drive/tests/<t>.sh` (mktemp+git+PASS/FAIL)

## What to unit-test vs compile-only (repo convention)
- Pure logic (marker parse, decideX, format, clamp) → extract + bun-test (RED first).
- tmux/git/vscode side-effect wrappers in startOrchestrator.ts → compile + manual E2E (documented at its top). Don't force awkward mocks.

## Verify tmux side-effects for real
- `tmux new-session -d -s throwaway 'sleep 60'` → run the exact command the code emits → read back / `has-session` → `kill-session`.
- set-option uses PLAIN `-t name` (tmux 3.4 reads `=name` literally for set-option); has-session/attach use `-t '=name'`.

## Verify the cross-repo .orches-* contract
Round-trip: write the file with the bash verb (`orches-integrate.sh stamp-meta ...`), then `bun run` a tiny script importing the REAL extension parser (`parseOrchesMeta`, `resolveContinueTarget`) to confirm it parses + behaves. Proves both sides agree.

## The continue-button pipeline (headless runs)
button → `launchContinueRun(project, sprints)` → `buildContinueKickoff(...,sprints)` = `/orches-drive --once [N]` → detached tmux → writes `.orches-run.json` (running) → `startSpinPoll` (2.5s) detects running→done, re-scans, re-renders, reaps the session. Marker is the ONLY completion signal (done marker is bare — capture session name WHILE running).
