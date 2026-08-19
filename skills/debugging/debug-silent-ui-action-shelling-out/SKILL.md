---
name: debug-silent-ui-action-shelling-out
description: 'Use when a UI button/command that shells out to a tool-generated helper script silently does nothing or opens a dead page — run the script by hand, reuse the factory''s sibling detectors, and kill…'
installer: auto-skill
created_at: 2026-08-19T08:22:43+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'debugging'
content_hash: 898fae13aeff0372f86bf688bec89c3b497979da2d2e33dfdf8c4934ac6062bc
---
# Debug a UI action that shells out to a generated helper script and silently does nothing

Use when a button/command in an editor extension, dashboard, or CLI wrapper "does nothing"
(or opens a dead page) and the work is actually done by a helper script the tool itself
generated into the target project (`.<tool>-<verb>.sh`, `run.sh`, `preview.sh`, …).

Two independent defects usually stack here. Find both — fixing one leaves the symptom.

## 1. Run the generated script by hand, first

Before reading any host code:

```bash
cd <project>; bash .<tool>-<verb>.sh; echo "rc=$?"
```

This costs one second and usually prints the exact refusal (`unknown stack`, `no such
target`). A non-zero rc here means the host code is innocent of *causing* the failure —
it is only guilty of hiding it.

## 2. Find the sibling detectors the factory already fixed

A generated script almost always re-implements project-shape detection (which dir holds
the app, which package manager, which entrypoint). The generator repo usually has 2-3
OTHER copies of that same detection — in its build gate, its test gate, its screenshot
gate. Grep the generator for them:

```bash
rtk proxy grep -n "maxdepth 3 -name package.json\|\*/\*/package.json\|_pkgdirs\|_app_root" <generator>
```

Read those. They carry dated comments about shapes that already broke them
(`backend/`+`frontend/`, `apps/web`, `packages/*`). **Reuse their rule verbatim** instead
of inventing a second formula — a second formula drifts.

Key ranking rule they usually encode: pick the candidate that has *a real screen*
(`index.html`, `src/main.*`, `app/`, `src/app/`, `pages/`), not the first candidate with
a `dev` script — glob order puts `backend/` before `frontend/`.

The path with **no automated gate running it** is the one that rots silently. When you
patch one detector, audit its siblings in the same pass.

## 3. Audit the host's spawn for the two silence amplifiers

Grep the caller for these exact shapes:

- **`stdio: "ignore"`** (or `>/dev/null 2>&1`) on the spawn → the script's own error
  message is destroyed. Redirect it to a per-attempt log file the UI can read back
  (truncate on each start so it describes THIS attempt), and surface its last non-empty
  line in the error toast.
- **A fabricated fallback return** on timeout (`return "http://localhost:3000"`,
  `?? defaultPort`, `|| "ok"`). This converts *"it failed"* into *"it works but the page
  is broken"* — the worst possible report. Return `null` and make the caller refuse to
  proceed.

When replacing a timeout fallback, keep long-but-legitimate boots alive: extend the wait
while the log file is still **growing** (cold `npm install` takes minutes), capped by a
hard ceiling. A static log = genuinely dead, return null now.

## 4. Add a dry-run seam so the detection is testable

The script boots a real server, so a test suite cannot run it. Add an env seam that
prints the decision and exits before any side effect:

```bash
[ "${<TOOL>_<VERB>_DRYRUN:-0}" = 1 ] && { echo "PLAN $APP :: $CMD"; exit 0; }
```

Then TDD every project shape as a fixture (root / monorepo / backend+frontend /
lockfile-in-subdir / node_modules-must-be-skipped / unknown-stack-still-exits-1) before
touching the generator.

## 5. Keep side-file paths at the project root

If the fix makes the script `cd` into a subdirectory, the pidfile/log must still land
where the host reads them. Do the `cd` inside the launched subshell only:

```bash
setsid bash -c "cd \"\$0\" && exec $CMD" "$APP" >"$LOGF" 2>&1 </dev/null & echo $! > "$PIDF"
```

## Verify

- generator suite green, plus the new shape fixtures
- host unit suite + typecheck green
- re-run the generator's install verb against the real broken project, then the dry-run:
  it must now name the right app dir
- a real boot writes the server's output to the log; the host no longer opens a browser
  when no URL appears
