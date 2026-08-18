---
name: click-through-ui-gate
description: 'Use when a browser-driven check must press a page''s controls (shoot popups / find dead buttons) — state-safe, self-repairing, honest about repeated controls.'
installer: auto-skill
created_at: 2026-08-18T11:09:44+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'browser-gates'
content_hash: 5f2097f261eff6b99cece229d79a9125456ee336229706229fd475de3874495f
---
---
name: click-through-ui-gate
description: Use when a browser-driven check must PRESS a page's controls (screenshot popups / find dead buttons) instead of only loading routes — makes the pass state-safe, self-repairing, and honest about repeated controls.
---

# Adding a click-through pass to a UI gate

A gate that only navigates routes sees each page's initial state. Pressing controls is how you find "the Add button opens nothing" and how you get a picture of a modal. But clicking inside someone else's app can log you out, navigate away, or write data — so the pass must verify *after* every click, not trust a word-list.

## Host it in an existing session, not a new browser

Find the verb that already drives a browser over CDP with a logged-in session and per-route navigation (in this codebase: the responsive/viewport check). Run the pass there, **after** that verb's measurements for the route.

- no extra boot, no extra page load, session cookie already present
- clicking after the numbers are taken means a click can never move a number already reported
- one viewport only (the widest) — modals are laid out for it

## Enumerate → group → click one per group

`querySelectorAll('button, [role="button"], summary, [aria-haspopup]')`, drop disabled / <8px / hidden, read `aria-label || innerText`, tag each survivor with `data-<ns>-ix="<i>"`.

⛔ **A list of N rows is N buttons but ONE control.** Deduping by label text fails because the row's data is in the label (`View 1001`, `View 1002`). The discriminator is the **parent**:

| candidates sharing a shape | meaning | keep |
|---|---|---|
| under ≥3 **different** parents | repeated row/card control | one per **first word** of the label |
| under the **same** parent | toolbar of distinct buttons | every label |

`shape` = tag + own classes + 3 ancestors (tag + first class). Print how many the representative stands for — collapsing silently reads as "this page has one button".

Cap in **groups**, not raw buttons (a real page lands at 3-8), and when the cap bites print how many groups were skipped and the env var that raises it.

## Two word-lists, both first-pass only

- deny: `delete|remove|clear|reset|logout|pay|confirm|submit|save|publish|send` + local-language equivalents → never clicked
- opener: `add|new|create|edit|filter|sort|search|menu|detail|view|open|upload` + local-language → anything else is `skip-not-opener`

They are cheap filters, **not** the safety mechanism. A button called "New session" can clear the cookie.

## The safety mechanism: verify after every click

Before: capture the page's text signature + `{url, visibleDialogCount}`. Click. Wait ~500ms. Capture again, then classify in this order:

1. **text signature == the login page's signature** ⇒ the session is gone. Re-run the existing login routine with the same config, navigate back to the route, re-tag the controls, log `logged-out`, continue. (This is what makes a mislabelled logout button harmless.)
2. **url changed** ⇒ log `nav`, navigate back, re-tag. Never screenshot this — a picture of another page filed as "popup" is fake evidence.
3. **visible dialogs went up** ⇒ `popup`; screenshot.
4. **text signature/length changed** ⇒ `changed`; screenshot.
5. **nothing changed** ⇒ `no-change`. This is the most valuable finding: a control that should open something and does nothing.

Then close what opened: send Escape, re-read the state, and **verify it closed** — else reload. Clicking on inside an open dialog means pressing its Save/Confirm and writing real data.

⛔ Count only dialogs that are actually visible (`getBoundingClientRect` + `visibility/display/opacity`): apps render modals into the DOM hidden from the start, so a raw count is identical before and after and detects nothing.

⛔ Before clicking index *i*, re-read that element's label in-page and refuse if it no longer matches the vetted string (`moved`). A re-render shifts indices, and the next index may be the Delete button nobody vetted.

## Keep it report-only, and keep it out of the verdict

- one line per control, prefixed (`interact: <route> [<vp>] <label> -> <verdict>`), all lowercase, label slugged to `a-z0-9-`
- ⛔ if the host shell counts states with a whole-line `grep -c 'OVERFLOW'|'ERROR'`, a button *named* "Error" would change the verdict — slugging to lowercase is what prevents that
- filter these lines out of the host's measurement table (they are not rows) and give them their own section in the log
- screenshots go in a **separate subfolder**. If a gate elsewhere counts distinct images the worker must open, adding popup shots beside the route shots raises that bar with every button — cost grows, information does not
- off switch + caps as env vars; assert the off switch produces a byte-identical verdict

## Fixture warning

A node test server serving this pass needs `process.on('uncaughtException', () => {})` and a `clientError` handler. The pass issues many navigations, so killing the browser at the end of a run EPIPEs an in-flight response and the server dies silently — which surfaces as a later test section failing with `ERR_CONNECTION_REFUSED`, i.e. red assertions that have nothing to do with the code under test.

Put the logout button **second** in the fixture and assert the later buttons still work; that one ordering choice is what proves the repair path instead of just proving nothing crashed.
