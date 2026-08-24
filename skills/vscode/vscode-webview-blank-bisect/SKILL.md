---
name: vscode-webview-blank-bisect
description: 'Use when a VS Code extension webview renders blank or sticks on its placeholder with clean logs. Bisects client vs host outside the IDE (real Chromium over CDP + a Bun vscode-module stub) before…'
installer: auto-skill
created_at: 2026-08-23T18:07:31+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude'
category: 'vscode'
content_hash: fa90bdb69aca697c01191c0e2cbb810ea809162f336de331b954a81896b76306
---
# Bisect a VS Code webview that renders blank / stuck on its placeholder

Use when an extension's webview panel shows only its initial HTML forever and the logs
are clean. The whole point: **decide client-vs-host OUTSIDE the IDE before touching code.**
Guessing here costs a reload cycle per hypothesis.

## 0. Know what is invisible

- A throw inside a webview reaches **no log** — not the extension host log, not a
  notification. "Logs are clean" is not evidence the host is fine.
- An `async` `onDidReceiveMessage` listener that rejects is **swallowed** by VS Code.
- `webview.postMessage()` returns `Thenable<boolean>`; `false` = not delivered. Almost
  nobody checks it.
- `acquireVsCodeApi()` may be called **once per webview context** and **throws** on the
  second call — a restored panel re-running the page in a live context dies on line 1.

## 1. Instrument first (one reload buys every future answer)

Append-only capped file, never allowed to throw, in the extension:

    panelLog(`open restored=${!!restored} hadPanel=${!!_panel}`)
    panelLog(`ready received`) / `push start` / `push DROPPED` /
    panelLog(`push posted delivered=${await panel.webview.postMessage(...)}`)
    panelLog(`dispose`)

Write to `~/.<app>/panels.log`, not an output channel — a file is readable afterwards by
anyone (or any agent) without knowing which channel to open.

## 2. Run the CLIENT in a real browser

The page script usually lives in a template literal in the compiled JS.

    # extract the template (verify it has no ${} substitutions first)
    python3 - <<'PY'
    s=open("out/webview/<panel>.js",encoding="utf-8").read()
    i=s.index("function renderShell"); j=s.index("return `",i)+8
    k=s.index("`;", s.index("</html>", j))
    open("/home/$USER/page.html","w").write(s[j:k])
    PY

Inject a stub `acquireVsCodeApi` **that throws on the second call** (match VS Code) and
collect `window.onerror`. Then drive it over CDP:

    chromium --headless=new --no-sandbox --password-store=basic \
      --user-data-dir=$HOME/.cache/probe --remote-debugging-port=9333 about:blank &
    # then a small Bun/Node script: fetch /json/list, open the ws, Runtime.enable,
    # Page.navigate, wait, Runtime.evaluate to read window.__posted / errors

- `--dump-dom` is **broken** in recent Chrome (prints nothing even for a trivial page).
  Use CDP.
- Snap chromium cannot read paths outside `$HOME` — put the file in `$HOME`.
- `pkill -f "remote-debugging-port=9333"` **kills your own shell** (self-match). Kill by
  PID from `ss -ltnp` instead.

## 3. Run the HOST without VS Code

Stub the `vscode` module with a Bun preload, then call the real compiled entry point:

    // preload.ts
    import { plugin } from "bun";
    plugin({ name:"vscode-stub", setup(b){ b.module("vscode", () => ({ exports: FAKE, loader:"object" })); }});

Capture the panel's `onDidReceiveMessage` handler in the fake `createWebviewPanel`, then
invoke it with `{type:"ready"}` and assert what it posts. This exercises the real
scan/read/render pipeline against real on-disk data.

## 4. Read the verdict

| client posts | host receives | meaning |
|---|---|---|
| yes (browser) | never (log) | webview→host broken: script not running in THAT panel — suspect double `acquireVsCodeApi`, a restored panel, or no `onWebviewPanel:` activation event |
| yes | yes, `delivered=true`, still blank | host→webview fine, client render threw — wrap the dispatch in try/catch and report |
| nothing in browser | — | the script itself is broken; the browser console names the line |

## 5. Fixes that make the class unreachable

- **Do not depend on the handshake.** After setting `html`, `setTimeout(…, 1500)` and push
  anyway; cancel it when `ready` arrives. A paint must not be hostage to one direction.
- **Boot beacon** as the first `<script>` in `<head>`: acquire the API once, stash it on
  `window`, post `{type:"boot"}`, install `window.onerror` → host. Main script reuses the
  stashed instance instead of acquiring again.
- **Client watchdog**: retry `ready` N times, then replace the placeholder with an
  actionable message. A spinner that lies is worse than an honest dead end.
- **Restorable panels**: `registerWebviewPanelSerializer` is useless on its own — you must
  ALSO add `onWebviewPanel:<viewType>` to `activationEvents`, or VS Code never activates
  the extension to hand the panel back and the tab is a husk running stale HTML.
- Identity-guard `onDidDispose` (`if (_panel !== panel) return;`) before clearing module
  singletons — a late dispose otherwise blanks the panel that replaced it.

## 6. Test it so it stays fixed

Run **every** `<script>` block of the shell in order in a DOM shim where
`getElementById` returns `null` for ids the shell lacks, and `acquireVsCodeApi` throws on
the second call. A test that only *parses* the script passes through all of this.
