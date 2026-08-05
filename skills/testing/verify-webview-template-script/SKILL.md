---
name: verify-webview-template-script
description: 'Use when changing an editor-extension webview whose HTML+JS lives in a template literal: extract the script, syntax-check it, verify DOM ids, and run it against a stub DOM with real data.'
installer: auto-skill
created_at: 2026-08-05T16:07:00+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'testing'
content_hash: d82548083c7d4baac214a043414e2eddd33e302ba55f35b30d32be60175b5d5d
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

## Notes

- Keep the harness in a scratch dir; it is a verification tool, not a committed test.
- If the panel takes an optional argument that changes its initial mode, run the
  harness once per mode — the initial-render branch is the one users hit first.
- A stub whose `addEventListener` records the handler also lets you invoke click
  delegation directly, if a handler is worth exercising.
