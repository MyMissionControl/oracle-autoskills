---
name: detect-claude-turn-end
description: Use when a supervisor must tell if a Claude Code agent pane is still working or has ended its turn — read the session transcript's last assistant record instead of scraping the TUI.
installer: auto-skill
created_at: 2026-08-03T09:40:45+07:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: agent-orchestration
content_hash: a6ed503a20888d35eef780e67f6294aa9d98167a35dd08413a12643c96f354df
---
# Detect whether a Claude Code agent's turn ended — from its transcript, not the TUI

Use when a supervisor process must know if an agent pane is **still working** vs **done and
waiting**, and screen-scraping the TUI keeps giving false readings across versions/modes.

## Why not scrape the pane

TUI footers change per mode and per version (e.g. a `manual mode on` footer that an older
regex never matched), and "ready" vs "busy" detectors often read different-sized tails of the
same pane, so the gap between turns reads as idle. Every such miss is silent.

## The deterministic signal

Claude Code appends one JSON object per line to `<projects-dir>/<slug>/<session-id>.jsonl`.

1. **Get the session id.** Register a `SessionStart` hook that stores it where the supervisor
   can read it — e.g. `tmux set-option -p -t "$TMUX_PANE" @<opt> "$session_id"`, reading
   `session_id` from the hook's stdin JSON. No-op when not under the supervisor, so it is safe
   globally. Resolve the file with `find <projects-dir> -name "$sid.jsonl"`.
2. **Read backwards to the last meaningful record.** Keep only `type` in
   `("assistant","user")`. Skip everything else — `file-history-snapshot`, `ai-title`,
   `attachment`, `last-prompt`, `queue-operation` records can appear *after* the final
   assistant record.
3. **Decide.** Last record is `type=assistant` with `message.stop_reason == "end_turn"` →
   turn ENDED. Anything else (`tool_use`, a `user` tool-result) → WORKING.
   Measured on a real transcript: `tool_use` 56 / `end_turn` 6 — the two never overlap.

## Rules that make it correct

- **Skip `isSidechain`.** A subagent finishing is not the agent finishing.
- **Ignore unparsable lines.** The final line is often half-written; that is normal, not an error.
- **Fail toward WORKING.** Unknown `stop_reason`, unreadable file, missing session id → report
  WORKING/UNKNOWN. Being slow is cheap; killing a live agent is not.
- **Check the completion artifact first.** If the agent signals completion by writing a file
  during its turn, that file lands *before* `end_turn` — so "ended + no artifact" is a genuine
  silent exit, never a race.

## What this unlocks beyond liveness

The same record carries the agent's final text (`message.content[].text`). When an agent ends
its turn to **ask a question** in plain prose — which modal/permission detectors cannot see —
the supervisor can surface the actual question instead of replying with a canned nudge and
looping.

## Shape it as two pure verbs

`turn-state <file>` → `WORKING | ENDED <epoch> | UNKNOWN:<reason>`
`turn-say <file> [maxchars]` → last assistant text, whitespace collapsed

Both take a path, so they are testable with fixture `.jsonl` files and need no live agent.
Build fixtures by copying the *shape* of real records, and cover: tool_use tail, user tail,
end_turn tail, meta-after-end_turn, sidechain end_turn, truncated last line, null stop_reason,
missing file, empty file, meta-only file.
