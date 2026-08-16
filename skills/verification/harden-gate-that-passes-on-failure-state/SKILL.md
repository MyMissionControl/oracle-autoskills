---
name: harden-gate-that-passes-on-failure-state
description: 'Use when a gate/check reports PASS but its own artifact shows the failure (screenshots of the login page, ''healthy'' while the app is down) — an optional user-supplied marker replaced the structural…'
installer: auto-skill
created_at: 2026-08-16T11:03:45+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude'
category: 'verification'
content_hash: 1be04bfb77bcf86591a9732a88cb0e880654de06d3559a3e96486da46b39f2a0
---
# Harden a gate whose PASS signal also exists in the failure state

Use when a check/gate/smoke-test reports success but the artifact it produced shows the failure
(screenshots all of the login page, "healthy" while the app 500s, "clean" while findings exist), or
when you are reviewing any gate that decides PASS from a substring/marker in output it does not control.

## The shape of the bug

    if (userSuppliedMarker) { ok = text.includes(userSuppliedMarker) }
    else                    { ok = structuralCheck() }

An **optional, user-supplied value REPLACES a structural check instead of adding to it.** A lazy or wrong
value therefore *disables* the strong check and the gate reports success from the failure state itself —
e.g. a marker that is the site's brand name, present on the very page you were supposed to have left.

Generalised test to run against any gate: **state the PASS predicate, then construct a concrete failure
state in which that predicate is still true.** If you can, the gate lies; if there is no independent second
signal that would catch it, it lies silently.

## Procedure

1. **Reproduce the lie as a test, before touching the code.** Build the fixture so the marker is true
   *in the failure state* (wrong credentials + a marker that appears on the error page). A test written
   after the fix passes immediately and proves nothing. Confirm it goes RED with the exact wrong verdict
   the human reported.
2. **AND, never OR.** Keep the structural check unconditional; the optional marker may only *add*.
3. **Discard a marker you can prove is non-discriminating** — capture the pre-action artifact and, if the
   marker is already present in it, drop it and say so loudly. Do NOT simply AND a bogus marker in: that
   converts a false positive into a false negative, which is the same bug with the sign flipped.
4. **Add an independent second layer that compares against the failure state's own artifact.** Hash/compare
   the produced output against a captured sample of the failure state. This catches what a
   uniqueness/diversity counter structurally cannot: a failure page that is genuinely *different* from the
   other outputs still counts as "one more distinct result".
   - Compute the comparison basis in **one place** and pass it through the existing record format. A second
     formula on the other side is a silent mismatch waiting to happen.
   - Guard the basis: `md5("")` is a valid hash. An unguarded empty signature matches every empty/slow
     result. Require a minimum length before comparing.
5. **Pair every strictness increase with a positive control and a time budget.** This is the step that gets
   skipped and it is the one that breaks production: a stricter conjunction takes *longer* to become true,
   so a count-based loop (`10 x 600ms`) that was fine for one condition silently fails all of them together
   and the whole feature falls back to its degraded path. Budget in **wall-clock**, expose it as an env knob,
   and add a test where the operation genuinely succeeds but the marker is useless.
6. **Exempt the legitimate look-alike.** The artifact that is *supposed* to resemble the failure state (the
   login route itself, a status page, a fixture) must be excluded by identity, not by luck. A warning that
   fires on every healthy run is how a gate stops being read.
7. **English token first, human language after** — `walled 2/4`, `still-at-login url=...`,
   `marker-never-seen X=...`. Anything a machine or a test greps must not be prose.
8. **Follow the verdict downstream.** Fixing the verdict string is half the job:
   - does every branch write the verdict where the *reader* looks for it (a log line, an exit code)? A
     reader that falls back to a default (`v="ran"`) turns an honest verdict into no verdict at all;
   - does a caller re-announce success over the top of it (`case PASS*) echo "everything worked"`)? Add the
     narrower arm *before* the broad one.
9. **Sweep for siblings before closing.** The same anti-pattern is usually one function away. Grep every
   place that reads user/LLM-authored config (manifest keys, env vars, plan files) and decides a verdict,
   and ask of each: replaces or adds? A neighbouring gate running the *unauthenticated / unconfigured*
   version of the same probe is the highest-value find.

## Traps measured the hard way

- A uniqueness counter is **not** a wall detector. Both are needed; they answer different questions.
- Image/binary digests are not a "same content" signal (encoders and cursors are non-deterministic) —
  compare extracted **text**.
- Adding a field to a fixed-arity record (a 5th column read by 4 variables) silently corrupts the last
  field and can make a downstream gate pass for free. Reuse an unused existing field instead.
- A pseudo-record on a channel where every line is a result (`#login`, `#meta`) must be filtered by an exact
  match the reader already performs; a new prefix is counted as a real result with empty fields.
- If the gate prints only to a stream the success path discards, the warning you added does not exist on the
  runs where it matters most.
