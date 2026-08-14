---
name: webview-layout-probe
description: 'Use when a webview/panel UI looks visually broken (clipped text, squeezed rows, truncated names) and its HTML lives in a source template literal. Extracts the template, stubs the host bridge, and…'
installer: auto-skill
created_at: 2026-08-14T11:22:39+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude-opus-5'
category: 'webview'
content_hash: 09ceac72a6dbde8276afe5fc35665e1fde8f04eefa0e86dcdece42416a10c0c7
---
## Measure a webview's layout in a real browser (no puppeteer, no CDP socket)

Use when a panel/webview UI "looks broken" (text cut off, controls clipped, columns
too narrow) and the HTML lives inside a template literal in source, so you cannot
just open a file. Reading CSS will not tell you a row was squeezed to 42px — measure it.

### Steps

1. **Extract the template.** The panel HTML is usually one big string returned by a
   render function: slice the source from `return \`<!DOCTYPE html>` to the closing
   `</body></html>`. Assert the slice contains no backtick — if it does, the extraction
   crossed a boundary (or the source has a real bug).
2. **Stub the host bridge** by inserting a `<script>` that defines
   `window.acquireVsCodeApi = () => ({ postMessage: m => (window.__POSTED ||= []).push(m) })`
   *before* the client script. Keeping the posted messages is what lets you assert
   "this click actually asked the host for the next page".
3. **Append a boot script** that fires the same messages the host would
   (`window.dispatchEvent(new MessageEvent("message", {data: {...}}))`) with realistic
   fixture rows — pull real data from the live API once and freeze it to JSON. Drive it
   off `location.hash` so one file renders several states.
4. **Probe geometry into the DOM, not the console**: the boot script measures with
   `getBoundingClientRect()` / `scrollHeight` / `getComputedStyle` and appends
   `<pre id="probe" style="display:none">JSON</pre>`.
5. **Run headless chromium twice** — once with `--dump-dom` (grep out the probe JSON),
   once with `--screenshot`. Always pass `--headless=new --disable-gpu --no-sandbox
   --password-store=basic --use-mock-keychain --virtual-time-budget=4000` and a
   throwaway `--user-data-dir`. No node WebSocket, no CDP, no npm dependency.
6. **Simulate interaction in the same boot script**: `el.click()`, then read the DOM
   again into the probe. This verifies pagination, tab switches and "did it call the
   host" without any test framework.
7. Screenshot **before and after** the fix at the user's actual panel width, plus one
   narrow width to check the responsive path.

### What to measure (the numbers that expose real bugs)

- `card.scrollHeight > rect.height` → content is being **clipped** by `overflow:hidden`.
- `getComputedStyle(grid).gridTemplateRows` → equal-sized rows in a scrolling grid means
  the rows were squeezed to fit the box. Fix: `grid-auto-rows: max-content` (with
  `auto`, a definite-height grid shrinks every row and the cards silently lose content).
- `el.scrollWidth > el.clientWidth` → the label is ellipsised; the column is too narrow
  or a sibling control is stealing the width.

### Gotcha

An element measuring `height > 0` is NOT proof it is visible — it can be fully clipped by
an ancestor. Compare against the ancestor's box.
