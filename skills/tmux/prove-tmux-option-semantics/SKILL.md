---
name: prove-tmux-option-semantics
description: 'Use when settling what a tmux option/command actually does on this build (window-size, default-size, resize-window side effects) while a live session must stay untouched: isolated sockets, nested…'
installer: auto-skill
created_at: 2026-08-18T20:42:15+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'subagent:tmux-sizing-probe'
category: 'tmux'
content_hash: 2c339379ae89a21f07b407bcb3e3470785bbb1f0d18167227e46fa9b5b7ec2da
edited_at: 2026-08-19T07:52:12+07:00
edited_by: claude-opus-5
---
Use when you must settle *what a tmux option actually does on this build* (window-size / default-size /
resize-window side effects, hooks, layouts) while a LIVE production tmux session exists that you must not
disturb. Man pages for tmux sizing are wrong/absent across versions — measure, don't cite.

## 0. Safety: never touch the default socket
Every experiment goes on your own socket: `tmux -L <probe> ...`. On the default socket only
`list-*` / `show-options` / `display-message -p` / `capture-pane`. End with `tmux -L <probe> kill-server`
for EVERY socket you opened, then prove death: `tmux -L <probe> list-sessions` must print
`no server running on ...`. Check `ls /tmp/tmux-1000/` for sibling agents' probe sockets and leave them.

## 1. Read the real doc, don't trust memory
    man tmux | col -b > /tmp/tmux.man
    grep -n -A10 '^ *<option-name>' /tmp/tmux.man
    grep -n '<the exact sentence someone quoted>' /tmp/tmux.man || echo "NOT IN THIS BUILD'S MAN PAGE"
A quoted sentence that isn't in this build's man page is a claim about a *different* version. Report that.

## 2. Get a client of an EXACT known size: nest tmux
A real attached client is the only way to test client-driven sizing. Outer tmux supplies the terminal:
    tmux -L <probe>outer new-session -d -s outer -x <W> -y <H>
    tmux -L <probe>outer set-option -t outer status off      # else the pane is H-1, not H
    tmux -L <probe>outer list-panes -t outer -F '#{pane_width}x#{pane_height}'   # confirm == WxH
    tmux -L <probe>outer send-keys -t outer:0.0 'tmux -L <probe> attach -t <sess>'
    tmux -L <probe>outer send-keys -t outer:0.0 Enter        # Enter as a SEPARATE call
Then read the inner side: `tmux -L <probe> list-clients -F '#{client_width}x#{client_height}'` and
`display-message -p -t <sess>:0 '#{window_width}x#{window_height}'`.
Expect `window_height == client_height - <inner status lines>`; report both, don't "fix" the off-by-one.

## 2a. Not every attached client is a human — `list-clients` lies to size logic
Code that asks "is anyone watching?" with `list-clients -F '#{client_name}'` counts clients that are
not screens. A control-mode client (`tmux -C attach-session -t <s> -f ignore-size`, what bridges/IDE
integrations use) is attached and focused but supplies NO geometry. Measured on 3.4:
`w=[80] h=[] control=1 flags=attached,focused,control-mode,ignore-size,UTF-8` — `client_height` is
EMPTY. So the correct viewer test is:
    tmux -L <probe> list-clients -t <s> -F '#{client_control_mode} #{client_height}' \
      | awk '$1!=1 && $2>0 {print; exit}'
To hold one open for a test it must not see EOF on stdin — `< /dev/null` exits instantly. Use a fifo:
    mkfifo "$TD/ctl.fifo"
    setsid tmux -L <probe> -C attach-session -t <s> -f ignore-size <"$TD/ctl.fifo" >/dev/null 2>&1 &
    exec 9>"$TD/ctl.fifo"     # keep it open; `exec 9>&-` to release
Note the failure is LATENT: with only an ignore-size client attached, flipping to `window-size latest`
does not visibly resize anything, so a size assertion still passes — assert the OPTION, not the size.

## 2b. Capture what the CLIENT actually SEES (not what the pane holds)
`capture-pane` on the inner pane returns the whole canvas, so it HIDES clipping bugs. The outer pane IS
the client's screen — capture *that*:
    tmux -L <probe>       capture-pane -p -S 0 -E <winH-1> -t <sess>:0.0   # canvas (may be huge)
    tmux -L <probe>outer  capture-pane -p -S 0 -E <H-1>    -t outer:0.0    # what the human sees
Diff them: identical => nothing clipped. For a window bigger than the client, tmux paints only a
`client_width x (client_height - status)` viewport at offset `[#{window_offset_x},#{window_offset_y}]`
(`#{window_bigger}`=1; tmux's DEFAULT status-right prints `[ox,oy]`, so use `-f /dev/null`). Measured on
3.4, offset FOLLOWS THE CURSOR and *centers* it: with viewport sx/sy and window w.sx/w.sy —
`cy < sy -> oy=0` · `cy > w.sy-sy -> oy=w.sy-sy` · else `oy = cy - sy/2`. So a TUI that ends its draw
mid-canvas lands in the MIDDLE of the client with dead blank rows below it, and since `cx` is small
`ox` stays 0 forever => every line is cut at the client width with NO wrap continuation row. Prove wrap
vs truncation with one long line carrying a marker char at col `client_width` and another at +1: both
present on two rows = wrapped; second marker absent = truncated.

## 2c. Prove causality by A-B-A intervention, not by correlation
Toggle ONLY the suspected option and measure the same program 3x: A(set) -> B(unset) -> A'(set).
If A and A' match and B differs, the option is the cause. Also vary the client size (outer
`resize-window -x 80`) and show the defect tracks the CLIENT while the window stays pinned.
Bonus differential: if some windows in the live session are healthy, `show-options -w -t <s>:<i>` each
one — the option present ONLY on the broken window is your answer before you probe anything.
NOTE: `set-option -t "$sess" window-size ...` (no `-w`) writes the option on the session's CURRENT
window only, so a caller doing this pins exactly one window — matching that differential.
Man-page trap on 3.4: window-size `manual` is documented "...and windows are resized automatically";
measured behaviour is the OPPOSITE (manual = never auto-resized). Trust the measurement.

## 3. Wait without sleep (foreground sleep is often blocked)
    for i in $(seq 1 600); do n=$(tmux -L <probe> list-clients -F '#{client_name}' 2>/dev/null|wc -l); \
      [ "$n" -gt 0 ] && break; done
Poll the *condition*, not the clock. Never `set -x` around a big busy loop — it floods the transcript;
redirect the loop's trace or drop `set -x` for it.

## 4. THE TRAP: one option probe per fresh session
An option's *side effects* are masked if any later command in the same block writes the same option.
Measuring "does command X flip option O?" requires a session where X is the ONLY thing that ran:
    tmux -L <probe> new-session -d -s probeN
    tmux -L <probe> show-options -w -t probeN:0 O    # baseline; blank output == unset locally
    tmux -L <probe> <command X>
    tmux -L <probe> show-options -w -t probeN:0 O    # the answer
Scope matters: an option may exist at server/session/window/pane scope. `show-options -t <sess> O` for a
*window* option silently resolves through the session's CURRENT window, so it can disagree with
`show-options -w -t <sess>:<idx> O`. Always print the scope you mean, and label blank output explicitly.

## 5. Reproduce the CALLER's sequence, not a clean minimal one
A single command in isolation often succeeds where the product fails. Read the real script and replay its
exact loop, including the "cosmetic" steps between the interesting ones (relayout, refresh, select-*).
Those intermediate steps change the active target and are usually where the failure is born.
Run the *control* (the unconfigured/default case) through the identical loop and quote the real error text
verbatim, with rc, rather than paraphrasing it.

## 6. Test the full lifecycle, not the happy state
For anything client-dependent, the bug usually lives in a transition. Walk the whole cycle and measure at
each step: detached -> attach small client -> (do work) -> detach -> **do the original operation again**.
An option that looks correct while detached can be permanently poisoned by one attach/detach round-trip.
The final re-do step is what turns "looks fine" into proof.

## 7. Then, and only then, test the candidate fix
If the declarative option can't hold the invariant, test an event-driven pair instead:
    tmux -L <probe> set-hook -t <s> client-attached "<restore-for-human> ; <relayout>"
    tmux -L <probe> set-hook -t <s> client-detached "<re-pin-for-headless> ; <relayout>"
    tmux -L <probe> show-hooks -t <s>
Then re-run the §6 lifecycle against it and show the operation now succeeds. Prefer relative layout
sizing (`main-pane-width 50%`) over absolute, so a small client can't collapse a pane to 1 cell.

## Reporting
Every claim carries the command + its real output. Separate "man page says", "measured on build V", and
"my inference". Note the build (`tmux -V`) on every size/layout claim — these semantics differ by version.
