---
name: fix-hover-rebuild-eats-clicks
description: Use when a click (often a 2nd click / hover-highlighting grid) does nothing and the element re-renders on mouseover; root-cause + fix for the mouseover-rebuild storm that eats clicks.
installer: auto-skill
created_at: 2026-07-17T04:14:35+00:00
created_session: 
trigger: error-recovery
created_by: claude
category: webview
content_hash: dee5b4910ceb8b1472636091fa1bb2c36321e2d3e5edf781756b0a596dfb04de
---
---
name: fix-hover-rebuild-eats-clicks
description: Use when a click in a webview/SPA does nothing (often the 2nd click of a two-step interaction, or clicks on a list/calendar/grid that highlights on hover) AND the element re-renders on mouseover/hover. Root-cause + fix for the mouseover-rebuild storm that eats clicks.
---

# Hover-triggered innerHTML rebuild eats clicks

## Symptom
A click "does nothing" — no handler fires. Classic tell: a two-step pick (e.g. click start, then click end on a calendar/range/list) where the FIRST click seems to work (highlights) but the SECOND does nothing, or any grid/list that highlights-on-hover swallows clicks.

## Root cause
A `mouseover` (or `mousemove`) handler rebuilds the hovered container via `container.innerHTML = ...` (or otherwise replaces the DOM node under the pointer). In Chromium, replacing the node under the pointer makes the browser re-fire `mouseover` on the fresh node → your handler rebuilds again → a re-render STORM. Because `click` only fires when `mousedown` and `mouseup` land on the SAME element, and the storm keeps swapping nodes, the click never fires.

## Fix (root cause, not symptom)
Split rendering into two paths:
1. **Structural rebuild** (`innerHTML = ...`, which creates new nodes): ONLY when the structure actually changes — different data, page, month, filter. Triggered by explicit actions (open, navigate), never by hover.
2. **Highlight / preview update**: mutate the EXISTING nodes in place — `container.querySelectorAll("[data-x]")` then set `.className` / `.style` on each. Never reassign `innerHTML`. Use this for hover-preview and for cheap state flips (selected, in-range).

First-click / selection changes that only alter highlighting should also use the in-place path, not a rebuild.

## Verify (headless, no browser needed)
Extract the inline `<script>` and run it in a Node `vm` with a DOM shim. Make the container's `innerHTML` setter (a) rebuild child nodes with fresh identity and (b) if a "pointer is over the container" flag is set, re-dispatch `mouseover` on the new node under the pointer (this models Chromium's re-fire). Guard recursion depth and count rebuilds:
- BEFORE fix: one hover/click while hovering => many rebuilds (storm), recursion cap hit.
- AFTER fix: hover => **0** `innerHTML` assignments; a follow-up click commits.
Assert rebuild-count-on-hover === 0 as a regression test.

## Notes
- Same family as "innerHTML rebuild recreates an animated node" (flicker), but the tell here is EATEN CLICKS / dead second-click, and the trigger is specifically hover.
- Delegated listeners on the stable parent survive innerHTML swaps — so the bug is NOT a lost listener; it's the mousedown/mouseup target mismatch during the storm.
