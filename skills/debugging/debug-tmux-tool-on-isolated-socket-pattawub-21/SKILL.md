---
name: debug-tmux-tool-on-isolated-socket-pattawub-21
description: Use when root-causing a bug in a tmux-driving tool while a live session may exist: reproduce on an isolated tmux -L socket via a PATH-wrapper, never touching production.
installer: auto-skill
created_at: 2026-07-24T07:11:45+00:00
created_session: 
trigger: reusable-workflow
created_by: pattawub
category: debugging
content_hash: 6c1d9f70ee39454f85076cc03a0c18496a59ce1a9dcc042355a376f9d98fd88a
edited_by: opus5-main
edited_at: 2026-07-29T05:38:47
---

Use when you must root-cause a bug in a tool that DRIVES tmux (pane layout, send-keys,
session options, join/break-pane) but a LIVE/production tmux session may be on the default
socket. Reproduce on a throwaway socket so you never attach/kill/send-keys to a session you
didn't create.

## Procedure
1. Make a PATH-wrapper `tmux` that pins every call to an isolated socket:
   - Write `<wrapdir>/tmux` = `#!/bin/bash` + `exec /usr/bin/tmux -L <sockname> "$@"`, `chmod +x`.
   - `export PATH="<wrapdir>:$PATH"` in the test shell.
   - Any script under test that calls bare `tmux` (e.g. a helper with `t() { tmux "$@"; }`)
     now hits `-L <sockname>` — NOT the default socket. Production is untouched.
2. Recreate the exact precondition sequence the tool runs (init → action A → action B …),
   using `sleep 600` panes instead of the real long process (no need to spawn the real app).
   - Instead of the real app, FAKE only the signals the tool actually reads: pane/session
     options (`tmux set-option -p -t <pane> @foo bar`) plus any on-disk file it looks up.
   - ⚠️ If the tool detects state via `capture-pane -p | tail -N | grep …`, WHERE the fake text
     lands decides the verdict — and getting this wrong cuts both ways:
     - Marker at row 1 of a 24-row pane falls outside `tail -N`, so EVERY branch reads as
       not-ready. That can be a test bug — but FIRST check the real app's geometry.
     - **Do not reflexively pad to the bottom.** Padding matches a full-screen TUI (vim, less),
       but an INLINE TUI (Claude Code, most REPLs) draws downward from the cursor and leaves the
       rest of a tall pane blank. There, raw `tail -N` really does return N blank lines in
       production — padding in the test hides a live bug instead of reproducing it.
     - Decide by measuring, not guessing: run the real app once, then
       `capture-pane -p | grep -n . | tail -3` and `display-message -p '#{pane_height}'`. If the
       last non-blank row ≪ pane height, the app is inline → write the test WITHOUT padding and
       expect the tool to cope (`grep -v '^[[:space:]]*$' | tail -N`, i.e. last N *non-blank*).
     - The dangerous direction is a busy/lock check: "can't see the busy marker" = "not busy" =
       the tool writes over a running process. Always test that branch on a pane TALLER than the
       app draws.
   - Add a hard guard before any mutation: abort if `list-sessions` on the socket shows a
     session you did not create — proof the isolation actually took effect.
3. Inspect with read-only formats, e.g.
   `tmux list-panes -s -t "=<S>" -F '#{window_name} [#{@orch_member}] #{pane_id} #{pane_active}'`
   and diff state BEFORE vs AFTER the suspect step.
4. When a step "fails silently", re-run it WITHOUT the `>/dev/null 2>&1` and print `rc=$?` —
   tmux errors like `create pane failed: pane too small` only show on stderr. A detached
   window defaults to 80x24; `set-option -t <S> window-size manual` + `resize-window -x N -y M`
   makes splits fit.
5. Cleanup: `tmux -L <sockname> kill-server` (via the wrapper it only kills the isolated
   server). NEVER run `tmux kill-server` on the default socket.
6. Keep the repro as a permanent regression test (assert the invariant, exit non-zero on fail).

## Guardrails
- Read-only ops on the DEFAULT socket are fine (`list-sessions`/`list-panes`/`display-message`);
  attach/kill/send-keys/set-option there are NOT — always use the `-L` wrapper for mutations.
- tmux 3.4: `display-message -t '=<S>'` reads session vars EMPTY on a detached session — use
  `=<S>:` (trailing colon); `list-panes`/`has-session`/`kill-session` accept bare `=<S>`.
