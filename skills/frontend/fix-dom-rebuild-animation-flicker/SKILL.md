---
name: fix-dom-rebuild-animation-flicker
description: Fix a spinner/animation that stutters every refresh tick — a full innerHTML rebuild recreates the animated node. Use when an animated element freezes on an interval in a webview/SPA.
installer: auto-skill
created_at: 2026-07-15T07:26:56+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: frontend
content_hash: 71b1ce51a9792177e70fe8da583209efe2c735fb468df3af5409bf2688a791a8
---
# Fix: animated element stutters on a periodic UI refresh (DOM-rebuild flicker)

**Symptom:** a spinner / rotating icon / progress glyph in a webview or SPA visibly
"freezes" or resets for a split second on a regular interval (~1-5s). Users often
guess "it refreshes itself" — usually correct.

## Root cause (verify, don't assume)
A self-refresh timer re-renders by replacing a container's `innerHTML` wholesale.
Rebuilding destroys + recreates the animated node, so:
- CSS `@keyframes` animations restart from 0% on the fresh node → visible jump.
- JS-ticker glyphs reset to their static template char until the next tick fires.

## Diagnose
1. Find the refresh timer: grep `setInterval|setTimeout|poll|requestAnimationFrame`.
   Its period matches the stutter cadence — confirm they line up.
2. Follow the timer to the render call. Confirm it does `el.innerHTML = ...` (full
   replace), not a targeted patch.
3. Confirm the animated node lives INSIDE that replaced container (a CSS class with
   `@keyframes`, or a JS ticker querying the node each tick).

## Fix A — skip-guard (lowest risk; best when most refreshes are no-ops)
At the top of the render fn, serialize the incoming data and bail if unchanged:

    var _lastKey = null;                        // outer scope, survives re-renders
    function render(m){
      var key = JSON.stringify([ ...fields that drive the DOM... ]);
      if (_lastKey !== null && key === _lastKey) return;   // nothing changed → don't touch DOM
      _lastKey = key;
      el.innerHTML = ...;
    }

CRITICAL: reset `_lastKey = null` whenever a DIFFERENT screen/view replaces the same
container, so returning to this view always re-renders (else you get a stale/blank view).
Result: animation runs continuously during stable data; one intentional redraw only when
data actually changes.

## Fix B — in-place patch (100% smooth, more code)
Don't rebuild; update only changed fields per row (`textContent`/`className`) and leave
the animated node untouched so its animation is never interrupted. Also handle
add/remove/reorder + event rewiring. Use only if Fix A's one-flicker-on-real-change is
unacceptable.

## Verify (headless, before the visual check)
- Compile / type-check the project.
- If the client JS is EMBEDDED in a template string, the compiler treats it as an opaque
  string and won't check it. Extract the `<script>` block, neutralize `${...}`
  interpolations (replace with a literal), and `node --check` the result.
- Confirm the BUILT/output bundle contains your change (grep it) — not a stale build.
- Final confirmation is visual: reload the app, watch the element across several refresh
  ticks with no stutter.

## Gotcha — concurrent editors
If another session/process may be editing the same file: check `fuser <file>` and mtime
first; re-read the exact edit region immediately before editing; anchor edits on unique
strings, not line numbers (line numbers drift when another session writes).
