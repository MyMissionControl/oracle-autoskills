---
name: tmux-status-clickable-copy
description: Use when making a tmux status-bar element clickable to copy a value to the system clipboard (OSC52), silently and without a bar repaint; also covers why hover cursor-shape is impossible.
installer: auto-skill
created_at: 2026-07-18T10:03:41+00:00
created_session: 
trigger: reusable-workflow
created_by: pattawub
category: tmux
content_hash: 016c05c7c691347f8ea52a15b0d660efa613e97344ba8a2709e9b2e28ed62b64
---
# Make a tmux status-bar element click-to-copy (and what's impossible)

Goal: clicking a chunk of the tmux status line copies a value to the SYSTEM clipboard, silently, without disturbing the rest of the bar.

## What is NOT possible (say so up front)
- **Pointer/hand cursor on hover**: tmux has no hover event for the status line and cannot set the mouse-cursor shape. The outer terminal owns the cursor; no protocol lets the app request a shape per-region. Don't attempt it.

## Mechanism (tmux 3.2+)
1. **Wrap the text in a user range** inside `status-format[0]` (or status-left/right):
   `#[range=user|MYTAG]#[fg=...] <text> #[default]#[norange]`
   Use a distinctive TAG (prefix it, e.g. `orc:copysid`) so it won't collide with tmux's built-in window ranges.
2. **Route the click** with a `-T root` MouseDown1Status binding that checks `#{mouse_status_range}` and KEEPS a fallback so normal window-click still works:
   ```
   bind -T root MouseDown1Status if-shell -F '#{m:MYTAG*,#{mouse_status_range}}' \
     "run-shell '<script> _click \"#{session_name}\" \"#{q:mouse_status_range}\"'" \
     "select-window -t ="
   ```
3. **Copy to the real clipboard via OSC 52** (works with no xclip/xsel/wl-copy installed — good for headless/RDP/VSCode-terminal):
   - Read the value for the ACTIVE pane: `sid=$(tmux display-message -t "$s" -p '#{@myopt}')`
   - `tmux set-buffer -w -- "$sid"`   ( `-w` = also push to terminal clipboard )
   - **Required once**: `tmux set-option -s set-clipboard on` — it's a SERVER option and defaults to `external`, which does NOT emit OSC 52 outward. Must be `on`.
   - **OSC 52 is unreliable through some terminals (e.g. VSCode integrated terminal): the tmux buffer gets set but nothing reaches the real clipboard.** On a Linux/xrdp/X11 box (DISPLAY set, `xrdp-chansrv` running), write the X CLIPBOARD selection DIRECTLY — `xrdp-chansrv` then syncs it to the user's local machine clipboard, and every VM app can paste it:
     `( export DISPLAY="$disp" XAUTHORITY="$HOME/.Xauthority"; printf '%s' "$val" | xsel -b -i )`
     Get `$disp` from `tmux show-environment -g DISPLAY` (falls back after xrdp reconnect), not a hardcoded value. `xclip -selection clipboard` works too. Keep `set-buffer -w` as well for in-tmux paste. If `xsel`/`xclip` isn't installed, install it — OSC 52 alone is not dependable here.

## Locking the value to a FIXED source (not the active pane)
Pane options resolve to the ACTIVE pane in `status-format`, so a per-pane value (e.g. each pane's own id) CHANGES when the user switches panes. If you must show/copy one fixed pane's value regardless of focus, mirror it into a SESSION option and read THAT:
- Writer (a hook, or init) detects the target pane and does `tmux set-option -t "$session" @myfixed "$val"`.
- Bar + copy read `#{@myfixed}` (session option = stable across active pane), with a per-pane fallback: `#{?@myfixed,#{@myfixed},#{@perpane}}`.
- Seed it at init from the already-captured pane option, AND re-mirror from the hook (the value may be captured AFTER init runs).

## Keep the click SILENT (don't repaint the whole bar)
- `tmux display-message` overlays the ENTIRE status line with its text for display-time — that reads as "the whole bar changed". If you want no visual change on click, do NOT call display-message (or any status repaint). Just set-buffer and return.
- There is no partial status message and no per-range highlight in tmux; feedback is all-or-nothing. Silent copy is one option.
- **Localized feedback WITHOUT the whole-bar overlay**: rebuild `status-format[0]` with ONLY the clicked cell's text swapped (e.g. `copied`), then revert after a beat. tmux repaints the status line but every other cell is byte-identical, so visually only that cell changes. Parameterize your bar builder with an optional label override for the cell. Revert with a detached timer that does NOT reflow panes: `tmux run-shell -b "sleep 0.9; '$SELF' _rebar '$session'"` where `_rebar` rebuilds the bar only (no select-layout / select-pane, which move focus). `run-shell -b` survives the click handler's own run-shell.

## Applying to an ALREADY-RUNNING session (bar was baked at init)
The mouse binding re-reads the script each click, so handler-logic changes take effect immediately. But the range markup lives in the baked `status-format[0]`; rebuild JUST the bar without reflowing panes:
```
bar=$(bash -c 'source <(sed "/^case /,\$d" "$1"); build_bar "$2"' _ "$SCRIPT" "$SESSION")
tmux set-option -t "$SESSION" 'status-format[0]' "$bar"
```
(strips the dispatch `case` block so only functions load; avoids select-layout / select-pane which move focus).

## Verify offline (no live session)
Throwaway session, set the pane option, invoke the click entrypoint directly, assert the buffer holds the FULL (untruncated) value:
```
tmux new-session -d -s _t; p=$(tmux list-panes -t _t -F '#{pane_id}'|head -1)
tmux set-option -p -t "$p" @myopt "FULL-VALUE"
<script> _click _t "MYTAG"; test "$(tmux show-buffer)" = "FULL-VALUE" && echo PASS
tmux kill-session -t _t
```
Note: the bar may DISPLAY a truncated form (`#{=8:@myopt}`) while the copy uses the full option value — keep those two independent.
