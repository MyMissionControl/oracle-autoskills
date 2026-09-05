---
name: render-check-auth-split-backend
description: 'Diagnose+fix render-check auth failures in a monorepo that splits frontend/backend, when boot only starts the frontend''s own dev server'
installer: auto-skill
created_at: 2026-09-05T23:47:47+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'john-oracle'
category: 'orches'
content_hash: 069b3c35c6275e9c91e47e6773ce8d763c3021863ab5f62a29365d0ccb214212
---
# render-check auth against a split frontend/backend monorepo

Use when a worker in a multi-agent build fleet must get a genuine authenticated
screenshot (login-gated routes) via a render-check/screenshot-gate tool, inside
a monorepo that splits frontend (`<web-dir>`, e.g. `apps/web`) and backend
(`<api-dir>`, e.g. `apps/api`) into separate apps, and the worker's zone forbids
editing `<api-dir>/**`, the tool's own acceptance/login config, or any root/script
files (running pre-existing scripts/servers is still allowed — only writing is
forbidden).

## Symptom chain (diagnose in this order — do not guess)

1. **Login fill fails** (e.g. `auth: fill-failed user=no-el`): the tool's default
   username-selector guess (commonly `input[name=username], input[type=email],
   input[type=text]`) matches nothing.
   - Root cause is usually a frontend `<input>` (or a wrapped `<Input>` component
     that forwards `type={type}`) with no explicit `type` prop. In React, an
     `undefined` `type` prop means the DOM attribute is omitted entirely — the
     input renders, but no selector keyed on `input[type=...]` will match it.
   - Fix: add the correct explicit `type="text"` (or similar) on the actual
     login username field in `<web-dir>`. This is a legitimate in-zone
     correctness fix, not a workaround — do NOT edit the tool's login-selector
     config even if the tool suggests it, since the real bug is in your own
     markup.
   - Confirm before editing: grep the render-check tool's own source for its
     selector-derivation function (e.g. `authLogin`/`_auth_js_login`) to see the
     exact default selector list, rather than assuming.

2. **Login still fails after the fill is fixed** (e.g. `auth: login-failed
   password-field-present` — fields fill but the page never navigates past
   login): check whether the backend is bootstrapped at all in this worktree.
   - `ls <api-dir>/.venv/bin/python` (or equivalent dep-install marker) — a
     fresh `git worktree` often never had backend deps installed.
   - If missing, run the repo's own pre-existing bootstrap script (e.g.
     `bash scripts/bootstrap.sh`) — this only installs dependencies, it does
     not edit code, so it stays zone-compliant even when `<api-dir>/**` is
     off-limits to write.

3. **Login STILL fails identically after bootstrap**: read the tool's own
   render log (e.g. `.orches-render.log` or equivalent) and look at the literal
   boot command it executed. If it only shows the frontend's own dev command
   (e.g. `$ (boot) vite`) and nothing for the backend, the tool's boot
   mechanism structurally only starts the target app directory's own dev
   script — it does NOT know about or start a sibling backend. This is a
   design limitation of the tool, not a bug, and is often anticipated by the
   project's own cross-role contract doc (look for a "parallel-judge" or
   similar note saying the frontend worker must ensure a backend is
   independently available).
   - Fix: manually start the backend's existing entrypoint yourself as a
     background process, e.g.
     `cd <api-dir> && nohup ./.venv/bin/uvicorn main:app --port <port> > /tmp/<worker>-api.log 2>&1 & disown`
   - Verify it actually came up before re-running render-check: tail the log
     for a startup-complete line, and hit the health endpoint
     (`curl -sf http://127.0.0.1:<port>/api/health`).
   - Running an existing server process is not "editing `<api-dir>/**`" — the
     zone restriction forbids writes, not process execution. This stays
     compliant even under a strict "must not touch backend zone" rule.

## After the fix

Re-run render-check once. Expect it to report full pass with an
"auth: logged-in" (or equivalent) marker, and to have captured N genuinely
distinct authenticated screenshots rather than N copies of the login-redirect
page — that distinctness (different heading text / nav state per route) is
the actual acceptance evidence, not just the pass/fail line.

## Verify

- Every login-gated route's screenshot shows visibly different content
  (heading, body text, active-nav-state) from both the login page and from
  each other — not just a non-empty file.
- The backend process you started stays up for the remainder of the task; no
  code was edited in the backend directory, only pre-existing scripts/binaries
  were executed.
