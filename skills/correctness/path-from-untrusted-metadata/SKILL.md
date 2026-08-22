---
name: path-from-untrusted-metadata
description: 'Use when a tool deletes or overwrites a path built from data it didn''t write (frontmatter, JSON, filenames): prove the join escape, red-proof with a victim dir, validate at the delete.'
installer: auto-skill
created_at: 2026-08-20T22:21:19+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'correctness'
content_hash: 0d77f4e5cf3a056f2ce75e23e7fddbb0df1f545ba0746bdb1bb2498754a81659
---
# Fix an rm -rf whose path came from data you don't own

Use when a tool builds a destination path out of values it did not write — frontmatter,
a JSON field, a filename, an API response — and then deletes or overwrites that path
(`shutil.rmtree`, `fs.rmSync`, `rm -rf`, `robocopy /MIR`). One bad value = an arbitrary
directory gone. Highest priority when the tool runs unattended (cron, hook, daemon).

## 1. Prove the two teeth of path joining before you argue severity

    python3 -c 'import os; print(os.path.join("/repo/skills", "/home/me/.config"))'
    # -> /home/me/.config      an ABSOLUTE segment discards every prefix
    python3 -c 'import os; print(os.path.normpath(os.path.join("/a/b/dest", "../../X")))'
    # -> /a/X                  a `..` segment walks out

Node's `path.join` keeps the prefix but `..` still escapes; `path.resolve` behaves like
Python. Check which one your code uses — the absolute-segment case only exists in some.

## 2. Establish whether it runs with nobody watching

    crontab -l | grep -n <tool>
    grep -rn '<tool>' ~/.claude/settings.json ~/.config/systemd/user/*.service

A weekly cron that also pushes is a different bug from a button a human clicks.

## 3. Red-proof with a victim directory, and assert on the NORMALIZED path

The trap that makes traversal tests lie: you assert at the path you *meant*, but the
join normalized somewhere else entirely, so the check passes while the escape happens.

    def escaped(root, *segs): return os.path.normpath(os.path.join(root, *segs))
    # victim = a dir OUTSIDE both roots holding one irreplaceable file
    # after the run: assert that file still exists, AND that escaped(...) does not

Write the malicious input BY HAND. The tool's own writer usually validates, so using it
to build the fixture produces a clean value and a green, worthless test. Then check the
filesystem for real debris (`ls /tmp`) — the first run of a good red-proof often creates
something outside the test's temp dir, and that artifact is your proof.

## 4. Validate at the destructive step, not at the writer

Writer-side validation is not a defence: the marker that says "I came from the trusted
writer" is usually one line of text anything can copy. Put the check where the delete is:

    _SEGMENT_RE = ^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$    # ONE directory name
    reject if: empty, "." , ".." , isabs(v), "/" or "\" or NUL in v, regex miss
    then, belt and braces: realpath(dest) must be inside realpath(root)

`realpath` is what catches a symlinked parent redirecting a name that looks clean.

## 5. Refusing must be LOUD, and must not break the happy path

- Report every refusal (stderr + a `rejected` key in the tool's JSON). A silent skip is
  indistinguishable from "nothing new" in a cron log — that is a second bug, not a fix.
- Before shipping, run the new validator over EVERY real input on disk and print how many
  it would refuse. "0 of N refused" is the evidence that you hardened without breaking.
- Keep a no-regression test that a clean run reports no refusals at all.
