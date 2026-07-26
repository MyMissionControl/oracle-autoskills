---
name: vscode-ext-split-pure-for-bun-test
description: Use when unit-testing a VS Code extension module and the runner (e.g. bun test) can't resolve 'vscode'; split pure logic from vscode-using orchestration.
installer: auto-skill
created_at: 2026-07-23T03:20:55+00:00
created_session: 
trigger: error-recovery
created_by: claude
category: vscode-ext
content_hash: d878a1760fb5281e0d0074713c66b803ca36a91a8a9d5ce55e9c82579d34c982
---
# Split vscode-using code from pure logic so `bun test` can run

## When
Adding a unit-tested module to a VS Code extension whose test runner cannot
resolve the `vscode` module (e.g. `bun test`). Symptom:
`error: Cannot find package 'vscode' from '.../<module>.ts'` even though
`tsc` compiles fine (tsc uses `@types/vscode`, the runtime module is only
present inside the extension host).

## Why
`import * as vscode from "vscode"` at the top of a module executes at import
time. Any test that imports that module — even just to reach a pure helper —
triggers the unresolved import and the whole test file errors out.

## How
1. Put PURE logic (parsers, matchers, guardrails, command-string builders) in
   its own module with NO `vscode` import. Unit-test this module directly.
2. Put the vscode-using orchestration (window.showX, env.openExternal,
   commands) in a SEPARATE module that imports the pure module. Tests never
   import this one.
3. If a "projects root" / config path is normally derived via a vscode-coupled
   helper, inline the small derivation (read the JSON/file directly) in the
   pure module instead of importing the coupled helper — keeps the module
   hermetic. Leave a comment noting it mirrors the coupled helper on purpose.
4. Verify: `<runner> test <pure-module>.test.ts` passes AND the project's
   compile step (`tsc -p ./`) stays clean.

## Generic shape
- `<feature>Scan.ts` / `<feature>Kill.ts`  → pure, vscode-free, tested
- `<feature>Stop.ts` / `<feature>Cmd.ts`   → imports vscode + the pure module
- webview/command wiring imports the orchestration module
