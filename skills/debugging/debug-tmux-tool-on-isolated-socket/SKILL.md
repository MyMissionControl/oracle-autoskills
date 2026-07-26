---
name: debug-tmux-tool-on-isolated-socket
description: Use when root-causing a bug in a tmux-driving tool while a live session may exist: reproduce on an isolated tmux -L socket via a PATH-wrapper, never touching production.
installer: auto-skill
created_at: 2026-07-24T07:11:45+00:00
created_session: 
trigger: reusable-workflow
created_by: pattawub
category: debugging
content_hash: d0d6ac6398e33a935c0944740a29947b4710a1256ce466324c2b0d957defa15d
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
