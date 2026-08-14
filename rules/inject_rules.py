#!/usr/bin/env python3
"""inject_rules.py — SessionStart hook: inject tier-1 (universal) + tier-2 (role) oracle rules.

Why a hook and not a shared file: a project CLAUDE.md `@import` cannot reach outside its own repo.
Probed 2026-08-14 on this box — `@../rules/x.md`, `@/abs/path/x.md`, `@~/.claude/x.md`, and a symlink
pointing outside the repo ALL fail to load; only paths at/below the repo work. So role rules cannot be
shared by import or symlink. A SessionStart hook reads any absolute path and is launcher-independent,
so it fires for `maw wake`, the MissionControl Team-up button, and /orches alike.

Contract:
  stdin  : the SessionStart hook JSON (may carry {"cwd": ...}); empty/garbage is tolerated
  stdout : {"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext": "<rules>"}}
           or NOTHING AT ALL when the session is not an oracle (non-oracle sessions pay 0 tokens)
  exit   : always 0 — a broken rules dir must never block a session from starting

An oracle is identified WITHOUT looking for `ψ/`: the shared soulbrew vault has one too, which would
have swept in every workspace-root session. The test is the repo dir name ending in `-oracle`, or an
explicit key in roles.json.

Stdlib only. Run the tests with:  python3 tests/test_inject_rules.py
"""
import json
import os
import sys

RULES_DIR = os.environ.get("ORACLE_RULES_DIR") or os.path.dirname(os.path.abspath(__file__))
ORACLE_SUFFIX = "-oracle"


def _read_stdin_json():
    """The hook payload. Never raise: a hook that dies on odd input is worse than one that guesses."""
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    if not raw or not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def resolve_cwd(payload):
    """Session cwd. The hook JSON wins over the process cwd: the hook may run from anywhere."""
    for key in ("cwd", "project_dir", "projectDir"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env and env.strip():
        return env.strip()
    return os.getcwd()


def load_roles(rules_dir=RULES_DIR):
    try:
        with open(os.path.join(rules_dir, "roles.json"), encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def oracle_name(cwd):
    """Repo dir name with a trailing '-oracle' stripped, lowercased. '' when the path is unusable."""
    try:
        base = os.path.basename(os.path.realpath(cwd)).strip().lower()
    except Exception:
        return ""
    if not base:
        return ""
    return base[: -len(ORACLE_SUFFIX)] if base.endswith(ORACLE_SUFFIX) else base


def is_oracle(cwd, roles):
    """True for an oracle repo. Dir-name suffix OR an explicit roles.json key — never a `ψ/` probe."""
    try:
        base = os.path.basename(os.path.realpath(cwd)).strip().lower()
    except Exception:
        return False
    if base.endswith(ORACLE_SUFFIX):
        return True
    name = oracle_name(cwd)
    return bool(name) and not name.startswith("_") and name in roles


def resolve_role(name, roles):
    role = roles.get(name) if not name.startswith("_") else None
    if not isinstance(role, str) or not role.strip():
        role = roles.get("_default")
    if not isinstance(role, str) or not role.strip():
        role = "worker"
    # A role name becomes a filename: keep it boring so roles.json can never reach out of the dir.
    role = role.strip().lower()
    return role if role.replace("-", "").isalnum() else "worker"


def _read_rule(rules_dir, filename):
    path = os.path.join(rules_dir, filename)
    try:
        with open(path, encoding="utf-8") as fh:
            body = fh.read().strip()
    except Exception:
        # Fail LOUD-but-open: say the file is missing rather than silently shipping fewer rules.
        return "[rules] MISSING %s" % filename
    return body or "[rules] MISSING %s (empty)" % filename


def build_context(cwd, rules_dir=RULES_DIR, roles=None):
    """The injected text, or None when this session is not an oracle."""
    roles = load_roles(rules_dir) if roles is None else roles
    if not is_oracle(cwd, roles):
        return None
    name = oracle_name(cwd)
    role = resolve_role(name, roles)
    parts = [
        _read_rule(rules_dir, "universal.md"),
        _read_rule(rules_dir, "role-%s.md" % role),
    ]
    body = "\n\n".join(parts)
    # Receipt line: a silently broken hook would otherwise look exactly like a working one.
    receipt = "[rules] %s · universal + role-%s · %d bytes · %s" % (
        name,
        role,
        len(body.encode("utf-8")),
        rules_dir,
    )
    return "%s\n\n%s" % (body, receipt)


def main():
    payload = _read_stdin_json()
    try:
        context = build_context(resolve_cwd(payload))
    except Exception:
        return 0  # never block a session
    if context is None:
        return 0  # not an oracle: emit nothing
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        },
        sys.stdout,
        ensure_ascii=False,
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
