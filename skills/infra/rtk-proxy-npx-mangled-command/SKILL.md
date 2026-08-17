---
name: rtk-proxy-npx-mangled-command
description: 'Recover when the rtk hook mangles a bash command (e.g. npx prisma db push/seed) into ''[rtk: No such file or directory]'' — rerun via rtk proxy'
installer: auto-skill
created_at: 2026-08-17T12:25:52+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'john-oracle'
category: 'infra'
content_hash: c603a4cf7a0e8297dc0e652613abd1d632b9f4107a0c9bbbe1e211b6432343ac
---
---
name: rtk-proxy-npx-mangled-command
description: Use when a bash command run through the rtk (Rust Token Killer) hook fails with "[rtk: No such file or directory (os error 2)]" even though the underlying tool (e.g. npx, prisma, any CLI) works fine when run directly — the rtk hook mis-rewrote/mis-filtered that specific invocation.
---

# Recover from an rtk-hook-mangled command

**Symptom:** A shell command (commonly `npx <tool> <subcommand> ...`, e.g. `npx prisma db push`,
`npx prisma db seed`) exits with output like:

```
[rtk: No such file or directory (os error 2)]
```

even though the underlying binary is installed and works when invoked another way. This is the
`rtk` hook (a token-optimizing CLI proxy that transparently rewrites certain shell commands)
failing to correctly translate/rewrite that specific command shape — it is not a real "file not
found" from the tool itself.

## Fix

Bypass the hook's rewriting for that one command by running it through `rtk proxy`, which executes
the raw command unfiltered:

```bash
rtk proxy npx prisma db push --accept-data-loss
rtk proxy npx prisma db seed
```

## How to confirm this is the actual cause (don't guess)

1. `which rtk` and `rtk --version` — confirm rtk itself is installed and working (e.g. `rtk gain`
   succeeds). If rtk itself is broken, this fix won't help — see rtk's own troubleshooting instead.
2. Re-run the exact failing command prefixed with `rtk proxy` — if it now succeeds and produces the
   real tool's normal output (not the bracketed `[rtk: ...]` error), the hook was the cause.
3. Only reach for this once — don't retry the un-prefixed command in a loop hoping it works; the
   hook's rewrite behavior for that command shape won't change between retries.

## When NOT to use this

- If the bracketed error text differs (a real ENOENT from the tool itself, e.g. a missing binary
  after `npm install` didn't run) — verify the binary/package actually exists first
  (`ls node_modules/.bin`, `npm ls <pkg>`) rather than reaching for `rtk proxy` as a reflex fix.
