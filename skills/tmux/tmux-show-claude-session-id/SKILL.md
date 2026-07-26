---
name: tmux-show-claude-session-id
description: Show each tmux pane's own Claude Code session id in the status bar; use when asked to display/track which claude session runs in a pane or add session id to a tmux statusline
installer: auto-skill
created_at: 2026-07-14T08:10:25+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: tmux
content_hash: 29212ec51662df12f19be86891dd77fa5ae33f4fab047ab1b486f382088061b1
---
---
name: tmux-show-claude-session-id
description: Show each tmux pane's OWN Claude Code session id in the status bar (or any tmux format). Use when asked to display/track which claude session runs in a pane, surface the session uuid for finding transcripts, or add session id to a tmux statusline/bar.
---

# Show a Claude Code session's own id in tmux

## The core problem (why the obvious paths fail — check first, don't repeat)
tmux cannot read the claude session id on its own, and neither can a plain script:
- There is **no `CLAUDE_SESSION_ID` env var** on the claude process (`tr '\0' '\n' < /proc/<pid>/environ` shows only `CLAUDE_CODE_*` build/feature vars).
- claude does **not keep its transcript `.jsonl` open** as an fd (`/proc/<pid>/fd` has no `.claude/projects/*.jsonl`).
- The session uuid is **not in argv** for claude started via a shell/tmux (only some GUI-entrypoint launches embed one, and it may not be the session id).

So the id must be **captured from inside the session** (a hook), then stored where tmux can read it.

## Mechanism: SessionStart hook -> pane-scoped tmux option -> status-format
1. **Hook script** (`<hook-script>.sh`) — reads the hook JSON on stdin, extracts `session_id`, writes it to a pane-local tmux option keyed by the pane the hook runs in. No-op outside tmux so it's safe globally:
   ```bash
   [ -n "${TMUX:-}" ] || exit 0
   pane="${TMUX_PANE:-}"; [ -n "$pane" ] || exit 0
   sid="$(cat | python3 -c 'import sys,json
   try: print(json.load(sys.stdin).get("session_id",""))
   except Exception: pass')"
   [ -n "$sid" ] || exit 0
   tmux set-option -p -t "$pane" @claude_session "$sid"
   tmux refresh-client -S 2>/dev/null || true   # repaint status now
   ```
2. **Register globally** in `~/.claude/settings.json` under `hooks.SessionStart` (omit `matcher` to fire on startup+resume+clear+compact). MERGE — never clobber existing PreToolUse/PostToolUse:
   ```json
   "SessionStart": [ { "hooks": [ { "type": "command", "command": "<abs-path>/<hook-script>.sh" } ] } ]
   ```
   Global is right when the sessions live in different repos (e.g. an orchestrator + workers). Validate: `python3 -c "import json;json.load(open(...))"` AND `jq -e '.hooks.SessionStart[]|.hooks[].command' <file>`.
3. **Read it in the bar** — pane options resolve for the **ACTIVE pane** in `status-format`/`status-right`, so each pane shows its own value automatically:
   ```
   #{?@claude_session,#{@claude_session},#{session_id}}
   ```
   (falls back to tmux's own `#{session_id}` when unset). Truncate with `#{=8:@claude_session}` for a short id.

## Verify the load-bearing assumption in isolation (don't disturb live sessions)
Spin a throwaway session, set the option differently on two panes, confirm a session-targeted format returns the ACTIVE pane's value:
```bash
tmux new-session -d -s _t -x100 -y20; tmux split-window -h -t _t
mapfile -t P < <(tmux list-panes -t _t -F '#{pane_id}')
tmux set -p -t "${P[0]}" @claude_session A; tmux set -p -t "${P[1]}" @claude_session B
tmux select-pane -t "${P[0]}"; tmux display-message -t _t -p '#{@claude_session}'  # -> A
tmux select-pane -t "${P[1]}"; tmux display-message -t _t -p '#{@claude_session}'  # -> B
tmux kill-session -t _t
```

## Backfill already-running panes (the hook only fires on NEW sessions)
Map each pane's cwd to its transcript dir and take the newest `.jsonl` (dedicated-repo sessions make this reliable):
```bash
tmux list-panes -s -t "<session>" -F '#{pane_id}|#{pane_current_path}' | while IFS='|' read -r pid cwd; do
  enc=$(printf '%s' "$cwd" | sed 's#[/.]#-#g')          # claude encodes / and . as -
  f=$(ls -t "$HOME/.claude/projects/$enc"/*.jsonl 2>/dev/null | head -1)
  [ -n "$f" ] && tmux set-option -p -t "$pid" @claude_session "$(basename "$f" .jsonl)"
done
```
Then force a repaint (re-set `status-format[0]`, or `refresh-client -S`).

## Gotchas
- Read the pane option **read-only** to verify (`tmux display-message -t <session> -p ...`); do NOT `select-pane` on a live session — it moves the user's focus.
- If the bar script file is a symlink into a repo, editing it hits LIVE sessions on next rebuild.
- End-to-end hook firing can't be observed in the same turn (SessionStart fires outside it) — functional-test the script by piping a fake `{"session_id":"..."}` into it inside a tmux pane, and rely on the backfill for immediate display.
