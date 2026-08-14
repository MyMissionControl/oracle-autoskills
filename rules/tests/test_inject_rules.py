#!/usr/bin/env python3
"""Tests for the oracle rules SessionStart hook. Stdlib only.  Run:  python3 test_inject_rules.py

Covers the failure modes that would be invisible in production: a non-oracle session getting swept in
(the shared soulbrew vault has a `ψ/` too), a role file that silently vanishes, and roles.json trying
to name a file outside the rules dir.
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(os.path.dirname(HERE), "inject_rules.py")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL %s%s" % (name, (" — " + detail) if detail else ""))


def run_hook(cwd, rules_dir, payload=None, env_project_dir=None):
    """Run the real hook as a subprocess. Returns (rc, stdout)."""
    env = dict(os.environ)
    env["ORACLE_RULES_DIR"] = rules_dir
    env.pop("CLAUDE_PROJECT_DIR", None)
    if env_project_dir:
        env["CLAUDE_PROJECT_DIR"] = env_project_dir
    stdin = "" if payload is None else json.dumps(payload)
    p = subprocess.run(
        [sys.executable, HOOK],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
    )
    return p.returncode, p.stdout


def context_of(out):
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def make_rules(tmp, roles, files=("universal", "role-worker", "role-orchestrator")):
    d = os.path.join(tmp, "rules")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "roles.json"), "w", encoding="utf-8") as fh:
        json.dump(roles, fh)
    for f in files:
        with open(os.path.join(d, f + ".md"), "w", encoding="utf-8") as fh:
            fh.write("# %s\nMARK_%s\n" % (f, f.upper().replace("-", "_")))
    return d


def main():
    with tempfile.TemporaryDirectory() as tmp:
        roles = {"_doc": "x", "_default": "worker", "foreman": "orchestrator", "bob": "worker"}
        rules = make_rules(tmp, roles)

        def oracle_dir(name):
            p = os.path.join(tmp, "repos", name)
            os.makedirs(p, exist_ok=True)
            return p

        # 1. explicit orchestrator
        rc, out = run_hook(oracle_dir("foreman-oracle"), rules)
        ctx = context_of(out) if out.strip() else ""
        check("orchestrator: rc0", rc == 0, "rc=%s" % rc)
        check("orchestrator: gets role-orchestrator", "MARK_ROLE_ORCHESTRATOR" in ctx)
        check("orchestrator: not given worker rules", "MARK_ROLE_WORKER" not in ctx)
        check("orchestrator: gets universal", "MARK_UNIVERSAL" in ctx)
        check("orchestrator: receipt names the role", "role-orchestrator" in ctx and "[rules] foreman" in ctx)

        # 2. explicit worker
        rc, out = run_hook(oracle_dir("bob-oracle"), rules)
        ctx = context_of(out)
        check("worker: gets role-worker", "MARK_ROLE_WORKER" in ctx)
        check("worker: not given orchestrator guardrails", "MARK_ROLE_ORCHESTRATOR" not in ctx)

        # 3. unknown oracle falls back to _default (NOT orchestrator)
        rc, out = run_hook(oracle_dir("newbie-oracle"), rules)
        ctx = context_of(out)
        check("unknown oracle: _default worker", "MARK_ROLE_WORKER" in ctx)
        check("unknown oracle: never orchestrator", "MARK_ROLE_ORCHESTRATOR" not in ctx)

        # 4. non-oracle dirs emit NOTHING — even with a psi vault (the soulbrew-root trap)
        ws = os.path.join(tmp, "soulbrew")
        os.makedirs(os.path.join(ws, "ψ"), exist_ok=True)
        rc, out = run_hook(ws, rules)
        check("non-oracle: rc0", rc == 0)
        check("non-oracle: no output despite psi/", out.strip() == "", "got %r" % out[:80])
        proj = os.path.join(tmp, "projects", "some-app")
        os.makedirs(proj, exist_ok=True)
        rc, out = run_hook(proj, rules)
        check("project dir: no output", out.strip() == "")

        # 5. stdin cwd wins over the process cwd
        rc, out = run_hook(proj, rules, payload={"cwd": oracle_dir("foreman-oracle")})
        check("stdin cwd wins", "MARK_ROLE_ORCHESTRATOR" in context_of(out))

        # 6. CLAUDE_PROJECT_DIR is used when stdin carries no cwd
        rc, out = run_hook(proj, rules, env_project_dir=oracle_dir("bob-oracle"))
        check("env project dir used", "MARK_ROLE_WORKER" in context_of(out))

        # 7. missing role file is LOUD, not silent
        rules2 = make_rules(os.path.join(tmp, "b"), roles, files=("universal", "role-worker"))
        rc, out = run_hook(oracle_dir("foreman-oracle"), rules2)
        ctx = context_of(out)
        check("missing role file: rc0", rc == 0)
        check("missing role file: says MISSING", "[rules] MISSING role-orchestrator.md" in ctx)
        check("missing role file: universal still there", "MARK_UNIVERSAL" in ctx)

        # 8. roles.json cannot name a file outside the rules dir
        evil = make_rules(os.path.join(tmp, "c"), {"_default": "../../../etc/passwd", "x": "y"})
        rc, out = run_hook(oracle_dir("zz-oracle"), evil)
        ctx = context_of(out)
        check("path traversal in roles.json is rejected", "passwd" not in ctx and "role-worker" in ctx)

        # 9. broken input / broken rules dir must not crash
        rc, out = run_hook(oracle_dir("bob-oracle"), rules, payload=None)
        check("empty stdin ok", rc == 0 and "MARK_UNIVERSAL" in context_of(out))
        p = subprocess.run(
            [sys.executable, HOOK],
            input="not json at all",
            capture_output=True,
            text=True,
            cwd=oracle_dir("bob-oracle"),
            env=dict(os.environ, ORACLE_RULES_DIR=rules),
        )
        check("garbage stdin ok", p.returncode == 0 and "MARK_UNIVERSAL" in context_of(p.stdout))
        rc, out = run_hook(oracle_dir("bob-oracle"), os.path.join(tmp, "does-not-exist"))
        check("missing rules dir: rc0", rc == 0)

        # 10. output is well-formed hook JSON
        rc, out = run_hook(oracle_dir("bob-oracle"), rules)
        try:
            data = json.loads(out)
            ok = data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        except Exception as exc:
            ok = False
            print("    json error: %s" % exc)
        check("valid SessionStart hook JSON", ok)

    print("\n%d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
