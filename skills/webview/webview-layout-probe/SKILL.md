---
name: webview-layout-probe
description: 'Use when a webview/panel UI looks visually broken (clipped text, squeezed rows, truncated names) and its HTML lives in a source template literal. Extracts the template, stubs the host bridge, and…'
installer: auto-skill
created_at: 2026-08-14T11:22:39+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude-opus-5'
category: 'webview'
content_hash: 299cc04242f71caea381160a1a940239f414a9178315a2bde2b1ea73cff86477
edited_at: 2026-08-20T09:51:25+07:00
edited_by: skills-mcp
---
## Measure a webview's layout in a real browser (no puppeteer, no CDP socket)

Use when a panel/webview UI "looks broken" (text cut off, controls clipped, columns
too narrow) and the HTML lives inside a template literal in source, so you cannot
just open a file. Reading CSS will not tell you a row was squeezed to 42px — measure it.

### Steps

1. **Get the HTML.** Two routes — prefer (b) when the extension compiles to JS:
   (a) **Slice the template** out of source: from `return \`<!DOCTYPE html>` to the
   closing `</body></html>`. Assert the slice contains no backtick — if it does, the
   extraction crossed a boundary (or the source has a real bug). Cheap, but regex over
   source is the step that invents phantom failures (it happily parses a `<script` that
   only appears inside a comment).
   (b) **Ask the extension for it**: hook `Module._load` to return a stub `vscode`
   (`window.createWebviewPanel` → a fake panel whose `webview.html` setter records the
   string; plus `Uri`, `ViewColumn`, `commands`, `workspace`, `EventEmitter`,
   `Disposable`), then `require("out/webview/<mod>.js")` and call its `open*Panel({
   subscriptions: [], extensionPath, globalState })`. You get the exact bytes the
   extension sets — zero extraction risk, no escaping questions. Compile first.
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

### Gotchas

- An element measuring `height > 0` is NOT proof it is visible — it can be fully clipped
  by an ancestor. Compare against the ancestor's box.
- **snap chromium cannot read or write outside $HOME.** `--screenshot=/tmp/<agent
  scratchpad>/x.png` fails with `Failed to write file ...: No such file or directory`
  even though the directory exists and is writable — confinement, not a path bug. Put
  the html AND the png under `$HOME/<throwaway>/`, then move them where you want.
- If firing the host's `MessageEvent` does not populate a list, do not reverse-engineer
  the message shape — set the container's `innerHTML` directly with a few fixture rows.
  For a layout question that is equivalent evidence and one line instead of ten.
- Shoot the **state you changed**, not just the resting one: for a hover/drag/active
  style, add the class in the boot script (`el.classList.add("drag")`) so the screenshot
  proves the rule resolves. A missing rule looks identical to a resting element.
