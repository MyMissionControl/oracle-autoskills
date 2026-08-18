---
name: verify-webview-template-script
description: 'Use when changing an editor-extension webview whose HTML+JS lives in a template literal: extract the script, syntax-check it, verify DOM ids, and run it against a stub DOM with real data.'
installer: auto-skill
created_at: 2026-08-05T16:07:00+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'testing'
content_hash: 9209ec2d5ecd9edaf36fffb04adb21a1113870a0e5a4166de95206fcd9741731
edited_at: 2026-08-18T15:19:46+07:00
edited_by: skills-mcp
---
# Verify a webview's HTML-in-template-string script actually runs

Editor-extension panels (VS Code webviews and similar) are usually generated as one
giant JS/TS template literal: `return \`<!DOCTYPE html> … <script> … </script>\``.
The compiler never parses inside that literal, so a typo, a stale `getElementById`,
or a renderer that returns nothing all compile clean and surface as a **blank panel**
at runtime. Unit tests don't reach it either — there is no module to import.

Three cheap steps prove it works without launching the editor.

## 1. Extract the script and syntax-check it

```ts
const src = fs.readFileSync(PANEL_SRC, "utf8");
const html = src
  .slice(src.indexOf("<!DOCTYPE html>"), src.lastIndexOf("</html>"))
  .replace("${dataPlaceholder}", "[]")   // one per interpolation in the literal
  .replace(/\\`/g, "`").replace(/\\\$/g, "$").replace(/\\\\/g, "\\"); // un-escape
const script = /<script>([\s\S]*?)<\/script>/.exec(html)[1];
fs.writeFileSync(OUT, script);
execFileSync("node", ["--check", OUT], { stdio: "inherit" });
```

First find every interpolation so none is missed: `grep -nF '${' <panel-src>`.
The un-escape order matters — backticks and `$` before backslashes.

## 2. Prove every DOM handle exists

The most common runtime break is code reaching for an element the HTML no longer
ships (renamed id, removed toolbar control). Diff them mechanically:

```ts
const ids = [...script.matchAll(/getElementById\("([^"]+)"\)/g)].map(m => m[1]);
const missing = [...new Set(ids)].filter(id => !html.includes('id="' + id + '"'));
if (missing.length) throw new Error("MISSING ids: " + missing.join(", "));
```

Do the same for `querySelector('…')` targets — print them and eyeball.

## 3. Run it against a stub DOM and REAL data

Syntax-valid is not "renders right". Execute the extracted script with a fake
`document`, then read back what it wrote to `innerHTML`:

```ts
const els = {};
const el = (id) => (els[id] ??= { id, hidden:false, textContent:"", value:"",
  placeholder:"", innerHTML:"", addEventListener(){}, classList:{ toggle(){} } });
let onMessage = null;
const code = script + "\n;globalThis.__api = { render, S, someInternalFn };";
new Function("acquireVsCodeApi", "document", "window", code)(
  () => ({ postMessage: (m) => sent.push(m) }),
  { getElementById: el, querySelector: (s) => el("sel:"+s), querySelectorAll: () => [] },
  { addEventListener: (_e, fn) => (onMessage = fn) },
);
```

Appending `globalThis.__api = {…}` is the trick that reaches module-scope functions
and state the script never exports. From there drive the real flow:

- call an internal action, assert on the captured `postMessage` payloads
- feed the host's reply through `onMessage({ data: {…} })`
- **use real data** from the production loader, not fixtures — it catches wrong field
  names and empty-state bugs that hand-made fixtures paper over
- flip state (`__api.S.view = "kanban"`) and re-`render()` to cover each view
- print `el("view").innerHTML` slices and read them

## 4. When layout matters, run the REAL page in a headless browser

A stub DOM cannot tell you that a flex row wrapped, a column collapsed, or that a
click actually reached its delegated handler. For those, capture the panel's real
HTML and open it in chromium.

Get the HTML by stubbing the editor module at require time (`Module._load` hook
returning a fake `vscode`), calling the panel's open function with a fake
`createWebviewPanel` that records `panel.webview.html`, and keeping the recorded
`onDidReceiveMessage` handler so you can drive the host protocol yourself:

```js
await handler({ type: "get_data", path: realProjectPath });   // host answers via postMessage
const payload = posted.find(m => m.type === "data");           // capture it
```

Then write the page out with three edits, serve it, and dump the DOM:

1. **Shim the host bridge or nothing runs.** `acquireVsCodeApi` does not exist in a
   browser, so `const vscode = acquireVsCodeApi();` throws on the script's FIRST line.
   The page still renders its static shell, so it looks fine — the give-away is that
   every element the script fills is empty. Replace that one line:
   `html.replace("const vscode = acquireVsCodeApi();", "const vscode = { postMessage: function(){} };")`
2. Append a `<script>` that dispatches the captured payload as a real message event
   (`window.dispatchEvent(new MessageEvent("message", {data: …}))`) so the page renders
   with production data.
3. Append a `<pre id="probe">` and fill it on a `setTimeout` with what you want to
   assert: row texts, `document.querySelectorAll("table").length`, and — for layout —
   `getBoundingClientRect()` tops/lefts of the children that must share one line.

Serve over `python3 -m http.server <port> --bind 127.0.0.1`; chromium under a sandbox
cannot read `file://` (it renders its own ~250KB error page, easy to mistake for a
success) and `--screenshot=` writes may vanish. `--dump-dom` is flaky — retry until the
output length is plausible. `--virtual-time-budget=N` fast-forwards the `setTimeout`s.

To exercise interaction, click inside that probe script. **Re-query the node after
every click**: a render that rebuilds `innerHTML` detaches the element you are holding,
so a second `row.click()` on the stale reference silently does nothing and reads as
"the toggle does not collapse". Assert on row counts before/after, not on the handle.

## Notes

- Keep the harness in a scratch dir; it is a verification tool, not a committed test.
- If the panel takes an optional argument that changes its initial mode, run the
  harness once per mode — the initial-render branch is the one users hit first.
- A stub whose `addEventListener` records the handler also lets you invoke click
  delegation directly, if a handler is worth exercising.
