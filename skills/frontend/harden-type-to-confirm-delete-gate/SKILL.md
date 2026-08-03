---
name: harden-type-to-confirm-delete-gate
description: Use when building or reviewing a 'type the name to confirm' destructive dialog: four bypasses that pass a normal test suite, and how to prove each is closed.
installer: auto-skill
created_at: 2026-08-03T12:07:39+07:00
created_session: 
trigger: complex-task
created_by: claude
category: frontend
content_hash: bc075fdf7565e31d6208aa80a7b19a513492bb645220497542685d13ba576b45
---
---
name: harden-type-to-confirm-delete-gate
description: Use when building or reviewing a "type the name to confirm" destructive-action dialog (delete <resource>, GitHub-style). Four bypasses that pass a normal test suite, and how to prove each is closed.
---

# Hardening a type-to-confirm destructive dialog

A two-step gate (ask -> retype the name -> delete) looks obviously correct and
ships green. These four defects survive a full unit suite. Check each before
calling the gate done.

## 1. The empty-string match

```js
const matches = typed.trim() === resource.name.trim()   // BUG
```

True when BOTH sides are empty. Any resource whose name is `""` or whitespace
lets step 2 open already armed. If the confirm button occupies the same footer
slot as step 1's "Yes, delete", one double-click destroys the resource with
zero typing.

Fix, both layers:

- UI: never compare against an empty phrase.
  `const phrase = resource.name.trim() || 'DELETE'` — a nameless resource must
  stay deletable, so substitute a fixed word rather than disabling the button
  (that locks out existing rows).
- API: reject blank/whitespace names at the schema boundary and store the
  trimmed form. An HTML `required` attribute rejects `""` but accepts `"   "`,
  and nothing guards a direct API call.

Verify: assert the button stays disabled with an empty input on a
whitespace-named resource, and that a blank name 4xx's on create AND update.

## 2. z-index scoped by an ancestor stacking context

An overlay rendered inline is trapped: if the trigger sits inside
`position: absolute; z-index: N`, that wrapper is a stacking context and the
overlay's `z-50` is scoped inside it. It cannot outrank a sticky header at
`z-30`, nor any later sibling wrapper at the same `z-10`. The scrim looks
modal; the header and every later trigger stay live on top of it — so an
admin aiming at the dialog can open a SECOND destructive dialog for a
DIFFERENT resource, stacked over the first.

Fix: portal the overlay to `document.body`.

Verify from pixels, not reasoning — build a faithful static repro of the real
DOM nesting and hit-test in headless chromium:

```js
document.elementFromPoint(x, y).id   // must be the scrim, not `nav` / `trigger2`
```

## 3. In-flight lock with no ceiling

The dialog correctly refuses to close while the request is in flight. But a
bare `fetch` with no `AbortController` neither resolves nor rejects on a
stalled socket, so `deleting` stays true forever: X, Escape, Back and the
backdrop are all disabled behind a full-viewport scrim. Only a reload escapes,
and the operator cannot tell whether the action happened.

Fix: `AbortController` + a timeout (~20s); on abort, say plainly that the
outcome is unknown and to reload. Thread an optional `signal` through the API
client rather than special-casing the component.

Also handle 404-after-retry: a lost success response makes the retry 404.
Reporting that as a failure leaves the row on screen insisting a deleted
resource exists. Treat 404 on delete as success.

## 4. The match test does not pin exactness — mutation-test it

Assertions like `wrongName -> disabled`, `casedName -> disabled`,
`exactName -> enabled` all pass under a substring rule too. "Make it
friendlier" (`includes` / `startsWith`) is the single most likely future edit,
and it would ship green while one keystroke arms the delete.

Prove the test discriminates: temporarily mutate the rule in a scratch copy,
point the runner at it, and confirm the suite goes RED.

```
mutant: typed.trim() !== '' && name.trim().includes(typed.trim())
run -> if still green, the test is worthless; add prefix cases
```

Add explicit near-miss cases: a single leading character, a proper prefix, the
name plus one trailing character.

## Bonus: what a delete leaves behind

Before shipping delete, prove the teardown with a throwaway integration test
that counts rows before and after — do not read the cascade declarations and
assume.

- SQLite does NOT enforce `ondelete="CASCADE"` unless `PRAGMA foreign_keys=ON`
  is issued per connection. ORM-level `cascade="all, delete-orphan"` only walks
  the relationships it is declared on — grandchildren reached only through a
  DB-level FK survive.
- `INTEGER PRIMARY KEY` without `AUTOINCREMENT` reuses freed rowids, so the
  next child row inherits the survivors. A stale `completed=true` attached to a
  brand-new row is the concrete harm, not a tidiness issue.
- Denormalised JSON keyed by the deleted id (per-user state blobs) is reachable
  by no cascade at all.

Prefer explicit teardown in application code over the pragma: it behaves the
same on SQLite and Postgres, and does not depend on a pool or an external tool
issuing the pragma.
