#!/usr/bin/env python3
"""Mechanical tests for auto_skill.py — the non-blocking skill writer.

Runs the CLI in a throwaway temp dir and asserts on its JSON output + the
files it writes. Dependency-free (stdlib only). Run:  python3 test_auto_skill.py
"""
import json
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "auto_skill.py")

_passed = 0
_failed = 0


def run(*args, cwd=None, env=None):
    """Invoke auto_skill.py, return (exit_code, parsed_json_or_None, raw_stdout)."""
    full_env = dict(os.environ)
    full_env.setdefault("AUTO_SKILL_SOURCE", "test-oracle")  # creator is mandatory
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, SCRIPT, *args],
        cwd=cwd, capture_output=True, text=True, env=full_env,
    )
    out = proc.stdout.strip()
    parsed = None
    try:
        parsed = json.loads(out)
    except Exception:
        pass
    return proc.returncode, parsed, proc.stdout + proc.stderr


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    work = tempfile.mkdtemp(prefix="autoskill-test-")
    skills = os.path.join(work, ".claude", "skills")
    try:
        # 1. create -> written, valid frontmatter + provenance
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nRun tests then `fly deploy`.",
            "--dir", skills, "--trigger", "reusable-workflow",
        )
        skill_md = os.path.join(skills, "deploy-fly", "SKILL.md")
        check("create returns created", js and js.get("status") == "created", raw)
        check("create exit 0", code == 0, f"code={code}")
        check("SKILL.md written", os.path.isfile(skill_md))
        content = open(skill_md).read() if os.path.isfile(skill_md) else ""
        check("frontmatter installer stamp", "installer: auto-skill" in content)
        check("frontmatter has description", "description: Deploy to Fly.io" in content)
        check("frontmatter has content_hash", "content_hash:" in content)
        check("frontmatter has trigger", "trigger: reusable-workflow" in content)
        check("frontmatter records creator", "created_by: test-oracle" in content)

        # 2. validate passes on the generated file
        code, js, raw = run("validate", skill_md)
        check("validate ok on generated", code == 0 and js and js.get("valid") is True, raw)

        # 3. idempotent: same name + same body -> exists-identical, no dup, exit 0
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nRun tests then `fly deploy`.",
            "--dir", skills,
        )
        check("re-create identical -> exists-identical",
              js and js.get("status") == "exists-identical", raw)
        check("re-create identical exit 0", code == 0, f"code={code}")

        # 4. conflict: same name, DIFFERENT body, no --force -> refused, exit != 0, original intact
        before = open(skill_md).read() if os.path.isfile(skill_md) else ""
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nTOTALLY DIFFERENT BODY.",
            "--dir", skills,
        )
        check("conflict -> refused-conflict", js and js.get("status") == "refused-conflict", raw)
        check("conflict exit != 0", code != 0, f"code={code}")
        check("conflict leaves original intact", open(skill_md).read() == before)

        # 5. --force overwrites on conflict
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nTOTALLY DIFFERENT BODY.", "--force",
            "--dir", skills,
        )
        check("force -> created", js and js.get("status") == "created", raw)
        check("force actually overwrote", "TOTALLY DIFFERENT BODY" in open(skill_md).read())

        # 6. invalid name rejected
        code, js, raw = run(
            "create", "--name", "Bad Name!", "--desc", "x",
            "--body", "y", "--dir", skills,
        )
        check("invalid name -> invalid", js and js.get("status") == "invalid", raw)
        check("invalid name exit != 0", code != 0, f"code={code}")

        # 7. empty description rejected
        code, js, raw = run(
            "create", "--name", "ok-name", "--desc", "",
            "--body", "y", "--dir", skills,
        )
        check("empty desc -> invalid", js and js.get("status") == "invalid", raw)

        # 8. stage mode writes to .pending-skills, NOT live
        code, js, raw = run(
            "create", "--name", "staged-skill", "--desc", "A staged one",
            "--body", "# /staged-skill\n\nbody", "--dir", skills, "--stage",
        )
        live = os.path.join(skills, "staged-skill", "SKILL.md")
        pend = os.path.join(skills, ".pending-skills", "staged-skill", "SKILL.md")
        queue = os.path.join(skills, ".pending-skills", "queue.md")
        check("stage -> staged", js and js.get("status") == "staged", raw)
        check("stage did NOT write live skill", not os.path.exists(live))
        check("stage wrote pending file", os.path.isfile(pend))
        check("stage appended to queue.md", os.path.isfile(queue))

        # 9. validate fails on malformed SKILL.md (no description)
        bad_dir = os.path.join(skills, "bad-skill")
        os.makedirs(bad_dir, exist_ok=True)
        open(os.path.join(bad_dir, "SKILL.md"), "w").write("---\nname: bad-skill\n---\n\n# /bad-skill\n")
        code, js, raw = run("validate", os.path.join(bad_dir, "SKILL.md"))
        check("validate fails on missing description", code != 0 and js and js.get("valid") is False, raw)

        # 10. list shows auto-skill skills
        code, js, raw = run("list", "--dir", skills)
        names = {e.get("name") for e in js} if isinstance(js, list) else set()
        check("list includes created skill", "deploy-fly" in names, raw)

        # 11. AUTO_SKILL_DIR env sets the landing dir when no --dir/--global
        env_dir = os.path.join(work, "envhome", "skills")
        code, js, raw = run(
            "create", "--name", "env-skill", "--desc", "Lands via env",
            "--body", "# /env-skill\n\nbody", env={"AUTO_SKILL_DIR": env_dir},
        )
        check("env: create ok", js and js.get("status") == "created", raw)
        check("env: landed in AUTO_SKILL_DIR",
              os.path.isfile(os.path.join(env_dir, "env-skill", "SKILL.md")), raw)

        # 12. explicit --dir overrides AUTO_SKILL_DIR
        code, js, raw = run(
            "create", "--name", "dir-wins", "--desc", "dir over env",
            "--body", "# /dir-wins\n\nbody", "--dir", skills,
            env={"AUTO_SKILL_DIR": env_dir},
        )
        check("--dir overrides env",
              os.path.isfile(os.path.join(skills, "dir-wins", "SKILL.md"))
              and not os.path.exists(os.path.join(env_dir, "dir-wins")), raw)

        # 13. creator is MANDATORY: no --source and empty AUTO_SKILL_SOURCE -> invalid
        code, js, raw = run(
            "create", "--name", "no-owner", "--desc", "should be refused",
            "--body", "x", "--dir", skills, env={"AUTO_SKILL_SOURCE": ""},
        )
        check("missing creator -> invalid", js and js.get("status") == "invalid", raw)
        check("missing creator exit != 0", code != 0, f"code={code}")
        check("missing creator wrote nothing", not os.path.exists(os.path.join(skills, "no-owner")))

        # 14. --source overrides AUTO_SKILL_SOURCE and is recorded as created_by
        code, js, raw = run(
            "create", "--name", "owned-skill", "--desc", "owned", "--body", "x",
            "--dir", skills, "--source", "bob-oracle",
        )
        owned = os.path.join(skills, "owned-skill", "SKILL.md")
        check("--source create ok", js and js.get("status") == "created", raw)
        check("--source recorded as created_by",
              os.path.isfile(owned) and "created_by: bob-oracle" in open(owned).read(), raw)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
