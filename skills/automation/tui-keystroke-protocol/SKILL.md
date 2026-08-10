---
name: tui-keystroke-protocol
description: 'Use when automating an interactive TUI from outside its terminal: measure its key protocol on a throwaway tmux session, then gate the committing keystroke on the confirm screen.'
installer: auto-skill
created_at: 2026-08-10T13:32:55+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'automation'
content_hash: 124e64374973bc91e515f79eea1603abac9a922eb9379a61f73c00ee1a419535
---
Drive an interactive TUI (a REPL, installer, picker) from outside its terminal — safely — by measuring its key protocol instead of guessing it, then verifying the screen before the committing keystroke.

Use when you must automate a UI that only exists as characters on a terminal: sending keys into a live process where a wrong key types into a prompt, answers the wrong thing, or destroys work.

## Why not just guess

A wrong keystroke into a blocked interactive process is unrecoverable and silent. Footers ("Enter to select · ↑/↓ to navigate") describe *one* screen, not the whole flow — the affordance you need (a Submit, a confirm tab) often carries **no key label at all**. Static fixtures in a repo's tests are also incomplete: they capture the screen someone happened to record.

## Procedure

**1. Reproduce the exact state in a throwaway session.** Never experiment against real work.

```bash
tmux kill-session -t "=probe" 2>/dev/null
tmux new-session -d -s probe -x 100 -y 34 -c /tmp '<the interactive program>'
until tmux capture-pane -p -t "=probe:0" | grep -q '<a string only the ready UI prints>'; do sleep 2; done
```
Drive it into the state you care about. Send text and the newline **separately** — many TUIs drop a trailing newline pasted in the same write:
```bash
tmux send-keys -t "=probe:0" -l '<literal text>'   # -l = literal, no key-name parsing
sleep 1
tmux send-keys -t "=probe:0" Enter
```

**2. Wait on a condition, never a sleep.** `until tmux capture-pane -p -t "=probe:0" | grep -q '<marker>'; do sleep 3; done` — fixed sleeps read half-drawn frames.

**3. Change ONE key, then capture.** After each key, diff the screen against the previous capture and write down what moved:
```bash
tmux send-keys -t "=probe:0" -l '2'   # or: tmux send-keys -t "=probe:0" Right
sleep 1.5
tmux capture-pane -p -t "=probe:0" | grep -n . | tail -20
```
Record for every key: what changed, **and what did not** — especially whether the cursor/selection moved. A protocol whose steps do not depend on cursor position is the only kind that is safe to replay blind.

**4. Prefer position-independent steps.** If a step needs "press ↓ N times", keep looking: a tab key, a digit, or a named key usually reaches the same place without depending on where you started.

**5. Find the confirm screen and make it your gate.** Most flows have a review/confirm step. That screen is free verification: parse it, compare it against what you intended, and only then send the committing key. If it disagrees, abort and hand control back to the human with the reason — never "try harder".

**6. Note what the confirm screen does NOT print.** Confirm screens often lack the footer/marker your main parser keys on. Anything that detects "a UI is open" must not be fooled by it, and the confirm parser must key on something else (a uniquely-labelled row).

**7. Capture the aggregate shape.** Multi-selection frequently collapses into one delimiter-joined line. Verify by **containment**, not by splitting on the delimiter — an item's own text can contain it.

**8. Finish the flow once, end to end, and confirm the program acknowledged it.** Then `tmux kill-session -t "=probe"`.

## Encode the result

- Whitelist the key names you will send; never pass arbitrary text through the same path (`send-keys` with unknown text types it into whatever has focus).
- Re-check the target state immediately before sending (it may have been answered elsewhere meanwhile).
- Put each observed key transition in a comment with the date and how it was observed, and freeze the captured screens as test fixtures verbatim.
- One small settle delay per key; poll for the next screen rather than sleeping for it.
