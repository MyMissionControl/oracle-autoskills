---
name: tmux-send-keys-enter-swallow
description: 'When tmux send-keys text+Enter fails to submit into a TUI/Claude-Code pane (text stuck in composer): send Enter as a separate call after a settle; multiline via buffer bracketed-paste.'
installer: auto-skill
created_at: 2026-07-16T03:27:56+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-opus-4-8
category: tmux
content_hash: 8701ecd2b1a75224d7e12562ae7ca06fff2dfa712a1321d216dfdd058222dc9c
---
# tmux send-keys Enter-swallow fix

## Symptom
You drive a TUI app (Claude Code, or any full-screen terminal UI) via
`tmux send-keys -t <pane> "<text>" Enter` in ONE call. The text lands in the
input/composer but is NOT submitted — it just sits there with the cursor.
Especially bad for multi-line text. A downstream poll then blocks for its full
timeout because the worker never actually started.

## Root cause
Modern TUIs enable bracketed-paste / fast-input detection. When tmux delivers
the text as a fast burst, the app treats it as a *paste*, so the trailing
`Enter` in the same send-keys call is absorbed as a literal newline in the
composer instead of a submit keypress.

## Fix — single line
Split the Enter into its own send-keys call after a short settle so it arrives
as a discrete keypress OUTSIDE the paste burst:
```bash
tmux send-keys -t "$pane" "$msg"
sleep 0.3
tmux send-keys -t "$pane" Enter
```

## Fix — multi-line text / brief
Don't inline a heredoc into send-keys. Write to a file, paste via a tmux buffer
with bracketed paste (`-p`), settle, then a discrete Enter:
```bash
buf="mybuf-$$"                                   # unique name if dispatches can overlap
tmux load-buffer  -b "$buf" "$brieffile"
tmux paste-buffer -b "$buf" -t "$pane" -d -p     # -p = bracketed (app won't run the newlines) · -d = delete buffer
sleep 0.5
tmux send-keys    -t "$pane" Enter
```

## Verify (live, deterministic)
Send a 2-line payload of `echo MARK_A` / `echo MARK_B` into a throwaway shell
pane; capture the pane. If BOTH lines RAN (their output is present, not merely
the echoed command) the Enter submitted. If they sit un-run in the composer,
the Enter was swallowed — the fix isn't applied.

## Also confirm "did it actually start"
After a real dispatch, don't assume success — grep `capture-pane` for a
processing-footer marker (Claude Code shows `esc to interrupt` only while
working) before entering a long poll. A swallowed Enter otherwise wastes the
poll's entire timeout budget before you notice.

## Ready-signal gotcha
When polling "is the pane ready to receive input", match the app's persistent
FOOTER strings over `tail -N` of the capture (Claude Code: `for shortcuts`,
`bypass permissions`, `to cycle`, `esc to interrupt`) — NOT `grep -qE '.'`
(any non-empty line), which matches the boot banner and dispatches too early.
The footer lives at the BOTTOM, so `tail` is correct for a full-screen TUI.
