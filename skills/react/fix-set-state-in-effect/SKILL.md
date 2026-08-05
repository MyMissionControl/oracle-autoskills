---
name: fix-set-state-in-effect
description: Fix ESLint react-hooks/set-state-in-effect (React 19) by deferring synchronous setState via queueMicrotask, even when called through a helper function
installer: auto-skill
created_at: 2026-07-15T15:40:42+00:00
created_session: 
trigger: error-recovery
created_by: jack
category: react
content_hash: f4c7ebdbefb0da137c8b53ecb87dde27ca731d75df9c64e0441f068bb3328844
---
## Fix `react-hooks/set-state-in-effect` (React 19 / eslint-plugin-react-hooks)

Symptom: ESLint reports "Calling setState synchronously within an effect can
trigger cascading renders" on a `useEffect` that kicks off a data fetch —
even a completely ordinary `setLoading(true)` / `setError('')` reset before
the fetch.

Key gotcha: the rule fires **even when the setState calls are not written
literally inline in the effect body** — it also fires when they happen
inside a separately-defined helper function that the effect merely calls,
e.g.:

```tsx
function load() {
  setLoading(true)   // still flagged, even though this isn't "in the effect"
  setError('')
  fetchThing().then(...).finally(() => setLoading(false))
}

useEffect(() => {
  load()              // <-- ESLint still flags the setState calls above
}, [])
```

Don't assume moving the calls into a named function or custom hook exempts
them — the rule traces into direct call sites at any depth from the effect,
not just top-level-of-effect syntax.

### Fix

Wrap only the *synchronous, top-of-flow* setState calls (the ones that fire
immediately, before any awaited/async work) in `queueMicrotask(...)` so they
run in a callback rather than the effect's/helper's synchronous call frame.
Leave the async `.then()/.catch()/.finally()` callbacks alone — those are
already fine.

```tsx
function load() {
  queueMicrotask(() => {
    setLoading(true)
    setError('')
  })
  fetchThing()
    .then((res) => setData(res))
    .catch((err) => setError(err.message))
    .finally(() => setLoading(false))
}

useEffect(() => {
  load()
}, [])
```

### Verify

Re-run eslint on just the touched file to confirm the specific rule clears
before re-running the full lint pass:

```bash
./node_modules/.bin/eslint path/to/file.tsx
```

(Use the local `node_modules/.bin/eslint` binary directly if a CLI proxy or
shell wrapper might be shadowing `npx eslint`/`eslint` with a different,
possibly unconfigured, global install — a stale global ESLint gives a
misleading "no config found" error instead of your project's real lint
result.)
