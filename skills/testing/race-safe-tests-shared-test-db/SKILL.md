---
name: race-safe-tests-shared-test-db
description: Write flake-free tests for stats/aggregate endpoints when the test runner parallelizes files sharing one test DB — use self-consistent or growth-tolerant assertions, not before/after diffs
installer: auto-skill
created_at: 2026-07-31T10:06:31+07:00
created_session: 
trigger: error-recovery
created_by: bob
category: testing
content_hash: b0a4fb109e6a167c524f109efee095974ef1a1ab5eb62db97efda50559bdacca
---
## When to use

Writing a test (Vitest, Jest, or any runner that parallelizes test *files* by default) that hits an aggregate/stats/list endpoint or query, in a suite where multiple test files share one physical test database (e.g. one sqlite file used by all `*.test.ts` files, reset once by a global setup rather than per-file).

## The problem

Test runners like Vitest run separate test *files* concurrently (separate worker threads/processes) by default, even though `it()` blocks *within* one file run sequentially. If several files insert/delete rows in the same shared database, any assertion that:
- compares a "before" snapshot to an "after" snapshot of shared aggregate state (counts, totals, "most recent N" lists), or
- cross-checks an endpoint's response against a separately-run "ground truth" query issued right after calling the endpoint, or
- assumes your own just-created row is *the* most recent / first / only one in a shared collection

...is racy: another file's concurrent write can land in the gap between your two reads. This produces intermittent failures — often 1-in-3 or worse — that pass most of the time in isolation (`vitest run path/to/this.test.ts`) but fail unpredictably in the full suite. Running the full suite once and seeing green is not sufficient proof of correctness for this class of test.

## The fix

Replace cross-referencing assertions with one of two safe patterns:

1. **Self-consistency**: recompute the value the code under test claims to have derived, using only fields from the *same single response payload*, and assert that recomputation equals itself. Example: if an endpoint returns `{count, cumulative}` pairs where cumulative should be a running sum, verify `cumulative === runningSum` by summing `count` across the same array — never compare against a second query. Same idea for derived percentages: recompute `Math.round(count / total * 100)` from the response's own counts and compare to the response's own percent field.

2. **Tolerant-of-growth**: when asserting an effect of your own action on shared state (e.g. "my upload should show up somewhere"), use `>=` / `toBeGreaterThanOrEqual` instead of exact equality, and avoid positional assumptions ("mine is index 0") in favor of structural ones ("the list is sorted descending and has at most N entries").

## Verifying the fix actually worked

A single passing `npx vitest run` proves nothing for this bug class — the race window may just not have been hit that time. Run the full suite several times back-to-back (e.g. a shell loop, 5 iterations) and confirm zero failures before trusting the fix. If you can determine the flake rate first (e.g. 2 failures in 3 runs before the fix), reporting "0 failures in 5 runs after" is much stronger evidence than "it passed once."

## Why this matters

The failure only shows up under real concurrency, which single-file test runs and lucky full-suite runs both hide. Treating "the suite is green right now" as proof invites reintroducing this exact class of flake later, and the fix costs nothing at runtime (no serialization, no config changes) — it's purely a matter of what the assertions are allowed to compare against.
