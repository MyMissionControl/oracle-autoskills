---
name: vscode-ext-headless-behavior-probe
description: 'Use when a VS Code extension change decides WHICH UI surface opens (terminal vs webview) and you need proof without launching VS Code: stub the vscode module via Module._load and run the real…'
installer: auto-skill
created_at: 2026-08-13T13:36:18+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'testing'
content_hash: 502afff32660022865c08de665f27755fccb8fe0b27b701b66c32fb8868b0b0d
---
# Verify a VS Code extension command headlessly (stub `vscode`, run the real compiled code)

Use when you changed an extension command whose effect is "which UI surface opens"
(terminal vs webview, which options, which shell command) and you need PROOF without
launching VS Code. Unit tests can't reach it — the logic sits in a file that imports
`vscode`, so it is excluded from the pure-logic test suite.

## Steps

1. Compile first: `npm run compile` (or `npx tsc -p .`). You will require the JS in
   `out/`, not the TS.

2. Intercept the `vscode` import with a `Module._load` hook, BEFORE requiring anything:

```js
const Module = require("module"); const orig = Module._load;
const seen = { terminals: [], commands: [], panels: [], shown: [] };
Module._load = function (req) {
  if (req !== "vscode") return orig.apply(this, arguments);
  return {
    TerminalLocation: { Panel: 1, Editor: 2 }, ViewColumn: { Active: -1, One: 1 },
    Uri: { joinPath: () => ({ fsPath: "/x", toString: () => "vscode-resource://x" }) },
    window: {
      createTerminal(o) { seen.terminals.push(o); return fakeTerm(o); },
      onDidChangeTerminalShellIntegration() { return { dispose() {} }; },
      createWebviewPanel(id, title) { seen.panels.push({ id, title }); return fakePanel(); },
      showInformationMessage() {}, showErrorMessage() {}, showWarningMessage() {},
    },
    workspace: { getConfiguration: () => ({ get: () => undefined }) },
    commands: { registerCommand() {} },
  };
};
```

3. **Make deferred work fire.** Extensions commonly delay `sendText` until shell
   integration is ready, with a ~2.5s timeout fallback. A stub with
   `shellIntegration: null` captures NOTHING if you `process.exit()` before the
   timer. Give the fake terminal a working `shellIntegration.executeCommand` so the
   command is delivered synchronously:

```js
const fakeTerm = (opts) => ({
  ...opts, exitStatus: undefined,
  shellIntegration: { executeCommand(c) { seen.commands.push(c); } },
  show() { seen.shown.push(opts.name); }, sendText(c) { seen.commands.push(c); }, dispose() {},
});
```

4. **Point config at a throwaway file.** Find the settings-path env override
   (`grep -n "process.env" <settingsFile>`; e.g. `MC_CONFIG_PATH`) and set it — never
   let the probe write the user's real config. Then flip the setting and re-run:

```js
fs.writeFileSync(process.env.APP_CONFIG_PATH, JSON.stringify({ some_mode: "chat" }));
for (const k of Object.keys(require.cache)) if (k.includes("/out/")) delete require.cache[k];
const { theCommand } = require("<abs>/out/commands/theCommand.js");
```
   Clearing `require.cache` for `out/` is what lets one process test BOTH modes —
   module-level config reads are otherwise frozen at first import.

5. Require by ABSOLUTE path if the probe script lives outside the extension dir, and
   print a table per mode: options passed, whether the surface was revealed, which
   panel opened, and the exact shell command (assert on its tail).

## Also catches

Running the compiled entry under this stub proves there is no **module-init import
cycle** (a new `commands/ -> webview/ -> commands/` edge showing up as `undefined`
at require time). If exports print as functions, the cycle is fine.

## Traps

- `--dump-dom` style browser checks verify LAYOUT, not this; use both when the change
  spans host logic and webview DOM.
- Don't assert on the whole command string; assert on the distinguishing part
  (`/tmux attach/`, the tail) so unrelated command edits don't break the probe.
