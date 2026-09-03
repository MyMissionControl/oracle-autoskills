---
name: verify-integration-gate-env-first
description: 'Use when a gate that passed in every worker''s checkout FAILs on the integration branch after merge — attribute it to the integration checkout''s own environment (deps never installed, stale worktree…'
installer: auto-skill
created_at: 2026-09-02T16:18:10+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'jack'
category: 'orchestration'
content_hash: 03309b5249493489dd7995d216ba7e77754957d71251a6e38d832a47044bca53
---
# Verify the integration branch's own environment before believing a post-merge gate FAIL

Use when a per-branch gate (render/screenshot, smoke, e2e) passed inside every worker's isolated
checkout, then the SAME gate reports FAIL on the integration branch right after merge. The tempting
reading is "merging broke it". Two boring causes explain most of these, and both are environment,
not code — believing the FAIL sends a worker to fix nothing.

## Steps

1. **Ask whether the integration checkout was ever provisioned.** Workers install dependencies inside
   their own worktree; the integration checkout may never have run install at all.
   `[ -d <root>/node_modules ] || echo "NOT PROVISIONED"` (adapt per ecosystem: `.venv`, `vendor/`,
   `target/`). A gate that boots a dev server in an unprovisioned checkout returns 500 on **every**
   route — the tell is that *all* routes fail identically, including the trivial ones.
   Read the gate log for a module-resolution error (`Can't resolve '<dep>'`), not an app error.

2. **Discount routes that are not routes.** A gate that discovers pages by walking the filesystem
   will walk leftover worker worktrees (`agents/<role>/src/...`) and report them as failing routes.
   Check whether the reported paths contain a worktree prefix, and whether those dirs still exist
   (`git worktree list` vs `ls`). Cleanup often runs *after* the gate, so the log outlives them.

3. **Provision, then re-run the same gate unchanged.** Install deps, create the env file from its
   example, run the project's own setup/seed command, then re-run the identical gate command. Do not
   edit the gate to make it pass. Record both results — the first FAIL stays in the report as an
   environment artifact, not as a defect.

4. **Check the gate's login credentials against what setup/seed actually creates.** A gate that logs
   in before capturing is only as good as its account. A credential a worker registered ad hoc inside
   its own worktree does not exist in a fresh checkout, so the gate silently captures the login page
   for every route. Symptoms: `login-failed`, `password-field-present`, or
   `screens N/M` where N is 1-2 while M is large — every "different" route rendered the same wall.
   Point the manifest at the account the seed command creates, and re-run.

5. **Open the shots, do not trust PASS.** After it passes, read the images: a route that renders an
   error card still counts as PASS. Confirm the post-login screens are distinct and the count of
   distinct screens matches the number of genuinely different pages.

## Verify

- negative control: re-run the gate in an unprovisioned scratch copy and confirm it FAILs the same
  way — that is what proves cause 1 rather than assuming it.
- after fixing credentials, `screens` must rise; if it stays at 1-2 the login still is not working
  and a PASS is meaningless.
- ⛔ never "fix" this by relaxing the gate, disabling the login step, or marking the role docs-only —
  each converts a real check into a check that cannot fail.
