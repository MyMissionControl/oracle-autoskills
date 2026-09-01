---
name: fix-pytest-wrapper-modulenotfounderror
description: 'Fix ModuleNotFoundError when pytest runs via a JS/shell wrapper (spawnSync/subprocess) instead of python -m pytest'
installer: auto-skill
created_at: 2026-09-01T13:43:06+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'john'
category: 'testing'
content_hash: 048c85b698c6c3492ec93e27d10954618267c9891929e0549e86c9a9e3e871d0
---
---
name: fix-pytest-wrapper-modulenotfounderror
description: Fix "ModuleNotFoundError" when pytest is invoked from a JS/shell wrapper script (npm run test, spawnSync, subprocess.run) but works fine when run manually with `python -m pytest` from the project root.
---

# Symptom

A wrapper script (e.g. an npm `scripts.py:test` entry, a Makefile target, a CI step) invokes the venv's `pytest` binary directly — typically via something like `spawnSync(venvDir + "/bin/pytest", [], {cwd: projectDir})` or `subprocess.run(["pytest"], cwd=projectDir)`. Tests fail to even collect, with:

```
ModuleNotFoundError: No module named '<app_package>'
```

...even though the package (`app/`, `src/<pkg>/`, etc.) clearly exists at `<projectDir>/<app_package>` and manually running the test suite from that directory "should" work.

# Root cause

Calling the `pytest` **binary** directly does not add the current working directory to `sys.path`. Pytest's default (`prepend`) import mode only adds the *first ancestor directory of the test file that lacks an `__init__.py`* to `sys.path[0]` — usually the `tests/` directory itself, not the project root beside it. So `from app.main import app` fails because `app/` is a sibling of `tests/`, not inside it, and the project root was never put on the path.

Running `python -m pytest` instead **does** work, because `python -m <module>` always prepends the current working directory to `sys.path[0]` before running — this is a general Python `-m` semantic, not a pytest-specific feature.

# Fix

1. Reproduce directly to confirm the diagnosis before touching anything:
   ```bash
   cd <projectDir>
   <venv>/bin/pytest -q          # reproduces ModuleNotFoundError
   <venv>/bin/python -m pytest -q   # passes
   ```
2. If you own the wrapper script: change it to spawn the venv's `python` executable with `["-m", "pytest", ...]` as args, instead of spawning the `pytest` executable directly.
   - JS example: `spawnSync(path.join(venvDir, "bin", "python"), ["-m", "pytest"], { cwd: projectDir })`
3. If you do NOT own the wrapper script (e.g. it's out of your zone/role in a multi-agent or multi-owner repo): do not silently route around it. Use the proven `python -m pytest` invocation directly wherever you need tests to actually pass (docs, CI override, your own verification), and separately flag the wrapper script as broken to whoever owns it, including the exact one-line root cause above so they don't have to re-diagnose it.

# Why this matters beyond one repo

This bites any project that wraps `pytest` behind a task runner in a language other than Python (npm scripts, Make, Rust xtask, Go build tags) whenever the test package imports something via an absolute-from-root import path. It's a very easy trap because the failure looks like a broken package structure or missing `__init__.py`, when the actual defect is only in *how the test runner is invoked*.
