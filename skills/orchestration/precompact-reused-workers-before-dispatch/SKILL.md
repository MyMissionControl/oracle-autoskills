---
name: precompact-reused-workers-before-dispatch
description: 'Compact carried-over worker agents before dispatching the next sprint, so they do not auto-compact mid-task and burn the sprint clock'
installer: auto-skill
created_at: 2026-09-05T23:52:52+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'jack'
category: 'orchestration'
content_hash: 8cb500e46bc696fcc88e45d8164dd576998e125e5eaf07408e57fc64e7a0cdf1
---
# Compact reused workers BEFORE dispatching the next sprint, not during it

Use when an orchestrator reuses the same worker agents across consecutive sprints. A worker that
finished the previous sprint near its context limit will auto-compact the moment the new brief lands
— and spend 10-15 minutes producing nothing while holding the brief.

## Symptoms
- `poll-any`/`poll-done` returns TIMEOUT twice with no commits and no `.orches-progress.md`
- the worktree has files but no commit at all
- `tmux capture-pane -t <pane> -p | tail -3` shows `Compacting conversation… (12m …)` and `ctx [██████████] 99%`
- the dispatch verb printed something like `compact-at-start SKIPPED:under-start-at ctx=<n> start_at=<bigger n>`
  — the engine's pre-compact threshold is larger than the worker's real context window, so the guard never fires

## Steps
1. **Before dispatching sprint N+1, read each reused worker's context meter first:**
   `tmux capture-pane -t <pane> -p | grep -o 'ctx \[[^]]*\] *[0-9]*%'`
2. Over ~70% → send `/compact` into that pane and wait for it to finish **while it holds no work**.
   Compacting an idle worker costs the same minutes but they run in parallel with your own prep,
   not against the sprint clock.
3. Only then dispatch. Verify the brief was written to disk (`<worktree>/.orches-brief.md`) so a
   later mid-task compact is survivable.
4. If a worker is already mid-compact holding a brief: do not re-send, do not wake a second instance.
   Let it finish, keep polling, and check disk (commits + progress file) rather than the pane.

## Verify
- after step 2 the meter reads well under the auto-compact line and the pane is idle
- first worker commit appears within a few minutes of dispatch instead of 15+
- ⛔ never "fix" the stall by re-dispatching or by minting a second worker on the same identity —
  a duplicated session collides on the same conversation state
