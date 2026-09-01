---
name: fix-render-check-dual-server-port-guess
description: 'Fix a render/screenshot check that FAILs boot when the dev script runs 2+ servers concurrently and the tool''s port-guess latches onto the wrong one''s announced URL; use when a frontend+backend…'
installer: auto-skill
created_at: 2026-09-01T12:24:36+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'john'
category: 'testing'
content_hash: 57024b0b72dd5a5ffed5462298b4b7562e9b838f539cbe75a577d879138b56cc
---
# Fix render-check dual-server port-guess failure

## When this applies

A visual/browser-based render-check (or similar screenshot/smoke-check) tool boots your
project's dev command, then "guesses" which port to poll by scanning the boot log for the
first `host:port` pattern it sees — rather than being told the port explicitly. If your
project's dev script (`npm run dev`, etc.) boots TWO OR MORE processes concurrently (e.g. a
frontend dev server AND a separate backend/side-service, via `concurrently` or similar), the
tool can latch onto the WRONG process's announced URL, especially when the secondary service
starts and prints its own listening URL faster than the primary one does (a Python/uvicorn
service typically boots faster than a Next.js/Vite dev server compiling for the first time).

Symptom: the check reports a boot timeout/failure (e.g. "NOT READY after 90s") even though the
actual app you care about is running fine — because the tool is polling the secondary service's
root path, which may not even exist there (e.g. a FastAPI app with only `/health`, no `/`,
returns 404 forever to a check that requires a 2xx/3xx response).

## Diagnosis

1. Read the check's own boot/render log. Grep for every `http://` or `:[0-9]{4,5}` occurrence —
   if more than one process announces a listening URL, note which appears FIRST chronologically.
2. If possible, read the check tool's source for its port-detection logic. Confirm whether it
   scans the WHOLE log for any matching URL pattern (order-dependent, fragile) rather than
   waiting specifically for the primary process's own announcement.
3. Confirm the secondary service's path being polled doesn't actually exist there (e.g. its
   framework returns 404 on `/` because it only defines other routes).
4. Don't assume a fix already applied elsewhere (e.g. a manifest file, a `BOOT:`/config field)
   actually changes this tool's behavior — check what the tool's boot command is actually
   *sourced from* (e.g. it may read `package.json`'s own `dev` script directly, ignoring a
   separate acceptance/manifest file other tooling reads). Verify empirically by re-running
   the check after the "fix" lands, don't take it on faith.

## Fix (when you can't edit the project's dev script or the checking tool itself — e.g. both
are out of your zone/repo ownership)

1. Find what makes the secondary service silent on its own — many services already have a
   "not set up yet" code path that exits immediately with just a warning, printing no URL at
   all (check its wrapper/launcher script). This is often intentional, for first-time clones
   before that service's runtime is installed.
2. Temporarily induce that same silent state by renaming/moving aside the secondary service's
   already-built runtime directory (e.g. a Python virtualenv folder, a compiled binary) RIGHT
   BEFORE running the check. This is safe ONLY when that directory is a generated, gitignored
   build artifact — never rename source code or anything tracked in git.
3. Run the check. It will now correctly guess/detect the primary process's port since the
   secondary process never announces anything to compete with.
4. Immediately restore the renamed directory in the same shell session, and confirm via
   `git status` that nothing else changed as a side effect.
5. Document this precisely in your handoff notes for whoever else will hit the identical
   failure (siblings working on the same dev-script contract) — including the empirical
   finding about whether an existing "fix" elsewhere (e.g. a manifest field) actually resolves
   this specific tool's behavior or not.

## Related gap to check for

The same class of check tool often auto-discovers routes to screenshot by scanning source
files (e.g. Next.js `page.tsx` files) and may deliberately SKIP dynamic-segment routes (paths
containing `[id]`-style brackets), since it can't know a real id to substitute. If your work
includes a dynamic route, it will silently never be captured by the automated pass — verify it
manually instead (e.g. a throwaway Playwright/Puppeteer script that logs in and screenshots the
specific URL with a real id from the seed data). When doing this manually alongside other
concurrent workers/processes on the same machine that may default to the same ports, boot your
verification server on an alternate port to avoid colliding with (or, worse, misattributing and
killing) a sibling process — always check a process's actual command/cwd before killing
anything you find on a "busy" port, since another worker's server can be listening there too.
