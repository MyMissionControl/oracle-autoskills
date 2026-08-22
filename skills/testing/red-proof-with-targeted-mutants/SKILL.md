---
name: red-proof-with-targeted-mutants
description: 'Use when a new pure module''s tests are green but you never watched them fail — break the impl once per decision and require the named test to go red; catches vacuous tests (runner-pinned TZ/clock…'
installer: auto-skill
created_at: 2026-08-21T14:34:57+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'testing'
content_hash: 5b4f425d30b9c0c86c4d84880d98c621888af4832a6d327436ee884f300f331e
---
# Red-proof a test suite with targeted mutants (and catch vacuous tests)

Use when you added tests for a NEW pure module (or a new branch in one) and cannot get an
honest "watch it fail first" — the module did not exist, so the only red you saw was
`Cannot find module` / `Export named 'x' not found`, which proves nothing about any
individual assertion. Also use when a test passes and you are not sure it *could* fail.

A module-level import error hides per-test red. One assertion at the wrong path, or a
clamp that swallows the wrong direction, passes forever while the bug ships.

## The move

After the suite is green, break the implementation ON PURPOSE, once per decision the code
makes, and require the *named* test to go red. A mutant that changes nothing means either
the code is dead or the test is vacuous — both are findings.

## Steps

1. **Back up the file and record its digest** — you will mutate the live file that the
   test imports; copying the whole dependency tree to a scratch dir is usually not worth it.
   ```
   cp <file> <scratch>/<file>.bak ; md5sum <file> | cut -c1-12
   ```
2. **List the decisions**, not the lines. One mutant per decision:
   - ordering between two rules (swap them)
   - each early-return / guard (delete it)
   - a boundary (`>` -> `>=`)
   - the kill switch (`if (!(x > 0)) return …` — delete it)
   - "unknown means say nothing" (coerce the unknown value instead)
   - the wiring itself (drop the argument the caller passes)
3. **Apply one mutant at a time with a script, not by hand**, and assert the anchor exists
   so a silent no-op cannot masquerade as a passing mutant:
   ```
   python3 -c "s=open(P).read(); assert OLD in s; open(P,'w').write(s.replace(OLD,NEW))"
   ```
4. **Run only the affected test file** and grep for `^\(fail\)` plus the pass/fail counts.
   Record WHICH test went red. Restore from the backup between mutants.
5. **Restore and prove it**: `md5sum` must match step 1 exactly. Say so in the commit.
6. **Any mutant that stays green = a gap.** Add the missing assertion, then re-run that
   mutant. Do not rationalise it as "covered indirectly".

## Vacuous-test traps this catches

- **The harness pins an ambient global.** Some runners force `TZ=UTC` (bun test does),
  freeze the clock, or fake the locale. A test that BUILDS its input with the same global
  the code reads shifts both sides together and can never see the bug. Fix: spawn a child
  process with the global set explicitly, and **assert the child really got it** before
  asserting the value — otherwise the guard is vacuous for the same reason.
- **A clamp hides one direction.** `Math.max(0, now - t)` turns every negative error into
  `0`, so a sign/offset bug only shows on inputs where the expected answer is non-zero.
  Assert a non-zero expected value, not just "not negative".
- **Asserting the path you MEANT.** For traversal/escape tests, compute where the join
  really lands (`normpath(join(root, seg))`) and assert on THAT. Otherwise the escape
  happens one level above your check and the test reports PASS.
- **A missing export kills the whole file**, so every per-test red is invisible. If you
  need one real per-test red before the code exists, copy the module + test to a scratch
  dir and mutate there.

## For code you cannot unit-test (imports the UI framework, etc.)

Read the source as TEXT and assert the wiring string is present (`expect(SRC).toContain(
"f(a, b, c)")`). Then red-proof it by deleting the argument. It is a weak test that
catches the strong failure: the pure logic is correct and simply never called.

## Report shape

"N mutants, each red at its own test: <decision> -> <test name>. File restored, md5
<before> == <after>." Anything less and you are claiming coverage you did not measure.
