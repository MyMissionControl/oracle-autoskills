---
name: verify-frontend-against-unmerged-backend-contract
description: 'Visually verify a frontend page whose data comes from unmerged backend endpoints, using a throwaway mock server + Playwright, when render-check only shows empty states or is stuck behind a login wall'
installer: auto-skill
created_at: 2026-08-17T00:46:20+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'jack'
category: 'orches'
content_hash: 1a117ec7a0d5065171fe352b516b349c2a3a17fff4911333bb53d83a68a0a8d6
---
---
name: verify-frontend-against-unmerged-backend-contract
description: Visually verify a frontend page whose real data comes from backend endpoints that haven't merged yet (parallel-role sprint), using a throwaway mock server + Playwright, when the project's own render-check tool can only show empty/error states or is stuck behind an unfilled login wall.
---

# Verify a frontend against an unmerged backend contract

## When to use
- You're the `<frontend>` role in a parallel-role sprint (e.g. `orches`-style orchestrator/worker split) and the sibling `<backend>` role's endpoints for this sprint aren't merged into your worktree yet.
- The project's automated screenshot/render-check tool either (a) only reaches empty/error states because the real endpoints 404, or (b) never gets past a login wall at all.
- You need real confidence that the fully-populated UI (cards, modals, editors, whatever the feature is) actually lays out correctly — not just that jsdom component tests pass, which don't do real CSS layout.

## Step 1 — check the login gate isn't the reason you've never seen an authenticated page
Before assuming a prior "PASS" render-check ever verified anything behind auth, check the acceptance/QA manifest file (e.g. `acceptance.md`) for its `LOGIN_USER`/`LOGIN_PASS` fields. If they're still the blank template:
- Seed a test account (env-based admin seed script, or a register call) and fill in real, project-seeded test credentials.
- A render-check that "passes" while every authenticated route redirects to the same login page proves nothing about those routes — it can stay that way across multiple sprints if nobody ever fills this in.

## Step 2 — get one real screenshot of the CURRENT (possibly incomplete) backend
Run the project's own render-check/gate tool once with the login fields filled in. This tells you the true current state:
- If it now shows real overflow/layout bugs on shared chrome (nav, layout shell) that were previously hidden behind the login wall, fix those first — they're likely pre-existing, not something you just introduced, but they're in your zone now that they're visible.
- If your new page only shows a graceful empty/error state because the backend endpoint 404s, that confirms your error handling works, but doesn't verify the populated layout.

## Step 3 — stand up a throwaway mock matching the contract's exact response shapes
To see the fully-populated UI without waiting on / touching the sibling role's zone:
1. Write a minimal HTTP mock (e.g. Python `http.server` subclass, no extra deps needed) implementing just the endpoints your page calls, returning fixtures whose field names/types match the design doc's documented contract exactly (not guesses).
2. Point your dev server's backend-target env var (e.g. `VITE_BACKEND_URL`, `NEXT_PUBLIC_API_URL`) at the mock instead of the real backend.
3. Drive it with Playwright (Python or Node) to: log in (or fake login by seeding localStorage/cookies if the mock doesn't need real auth), exercise the actual interactions (filters, modals, edit-and-save, uploads), and screenshot at every required viewport.
4. Read the screenshots yourself. This catches real overflow/overlap/missing-content bugs that jsdom-based unit/component tests cannot, because jsdom never does real layout.
5. Never commit the mock server or its fixture files — keep them entirely in a scratch/tmp directory outside the repo. It's a verification tool, not a deliverable.

## Step 4 — switch back and re-run the official gate
After confirming the UI visually via the mock, point the dev server back at the real backend and re-run the project's actual render-check one more time. The mock was only to prove the UI *can* render correctly with correct data — the last state you leave the worktree in should reflect the real, current (possibly still-incomplete) backend, so the orchestrator's own gate sees the true state.

## Gotchas
- **Port conflicts with the render-check tool's own boot.** If you manually started a dev server for testing and left it running, the render-check tool's own `npm run dev` (or equivalent) may find the port taken, silently increment to the next port, and then report something like `SKIP:port-busy` because it can't prove the response came from its own boot. Kill any dev server you started manually (by PID from `lsof -i :<port> -sTCP:LISTEN`, not a broad `pkill -f` pattern that could match your own shell) before invoking the project's official check tool.
- **Document your assumptions.** When you write frontend code against a contract whose backend isn't merged yet, explicitly note in your handoff/notes file which response shapes you assumed (e.g. "raw text body, not JSON-wrapped" for a file-content endpoint) so the integrator can spot a mismatch quickly once the real backend lands.
