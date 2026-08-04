---
name: rtl-await-content-not-wrapper-testid
description: Fix RTL tests that race a fetched-content assertion against a component's synchronously-rendered wrapper testid, before its async fetch resolves
installer: auto-skill
created_at: 2026-08-04T11:17:33+07:00
created_session: 
trigger: error-recovery
created_by: mike-oracle
category: testing
content_hash: 9d69319b577e7d8000bb8e0297e213e5c639e90ea93ed3067f9d1cd06e0ab6e1
---
---
name: rtl-await-content-not-wrapper-testid
description: Fix intermittent React Testing Library failures where a fetched-content assertion runs right after the component's wrapper testid appears, but before its async fetch resolves.
---

## Symptom

`await screen.findByTestId('some-container')` (or `await waitFor(() => expect(screen.getByTestId('some-container')).toBeTruthy())`) resolves immediately. The very next assertion — checking for text/data the component loads asynchronously (e.g. `getByText(someValue)`) — fails with "unable to find element," and the printed DOM shows the component's own loading state (`กำลังโหลด...`, `Loading…`, a spinner) instead of the expected content.

## Root cause

A component that unconditionally renders its outer wrapper (`<section data-testid="foo-section">` / `<div data-testid="panel-x">`) but conditionally renders `loading ? <LoadingState/> : <RealContent/>` inside it satisfies `findByTestId` / `waitFor(testid)` the instant it mounts — before its `useEffect` fetch resolves. Waiting on the wrapper's existence proves nothing about whether the async data has actually loaded. This reproduces reliably (it's an await-ordering bug in the test, not a flaky timing race in the app).

## Fix

1. Never assert fetched content in the same statement/line as acquiring the wrapper. Split them.
2. `waitFor` (or `findBy*`) on the actual async-rendered CONTENT — specific text, a row testid that only appears post-load, an option that only exists once data arrives — not on the wrapper/container testid.
3. If you need the container reference first (e.g. via `findByTestId`, to scope later `within()` queries), follow it immediately with a `waitFor` on content inside that container, before doing anything else with it:
   ```
   const panel = await screen.findByTestId('panel-x');
   await waitFor(() => expect(within(panel).getByText(expectedValue)).toBeTruthy());
   // only now is it safe to read further state from `panel`
   ```
4. Apply the same rule anywhere a fetch-on-mount + `loading` boolean + unconditionally-rendered wrapper pattern exists — list sections, detail panels, modals that fetch on open, etc.

## When this bit twice in one file

Two different tests in the same suite hit this independently: one on a dashboard's section-switch (`waitFor` on the new section's testid, then an immediate `getByText` for its list content), one on an expandable panel (`findByTestId` for the panel, then an immediate `getByText` for a member's name). Same root cause both times — a reminder to grep a new RTL test file for `getByTestId(...)).toBeTruthy()` / `findByTestId` immediately followed by a non-`waitFor` content assertion before trusting it's race-free.
