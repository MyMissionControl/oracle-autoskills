#!/usr/bin/env python3
"""v2 fleet-tools tests: collect_commit (single-committer, dedup/rename) + sync_skills
(flatten into a skills dir, archive removed). Uses the real auto_skill.py writer to
produce source skills. Stdlib only.  Run:  python3 test_v2.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))          # tools/tests
TOOLS = os.path.dirname(HERE)                               # tools
REPO_ROOT = os.path.dirname(TOOLS)                          # oracle-skills
WRITER = os.path.join(REPO_ROOT, "auto-skill", "scripts", "auto_skill.py")
COLLECT = os.path.join(TOOLS, "collect_commit.py")
SYNC = os.path.join(TOOLS, "sync_skills.py")

_p = _f = 0


def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1; print(f"  PASS  {name}")
    else:
        _f += 1; print(f"  FAIL  {name}  {detail}")


def sh(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout.strip()), r.stdout + r.stderr
    except Exception:
        return r.returncode, None, r.stdout + r.stderr


def make_skill(src, name, source, category, body):
    return sh(sys.executable, WRITER, "create", "--name", name, "--desc", f"{name} skill",
              "--source", source, "--category", category, "--dir", src, "--body", body)


def count_commits(repo):
    r = subprocess.run(["git", "-C", repo, "rev-list", "--count", "HEAD"],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "?"


def main():
    work = tempfile.mkdtemp(prefix="v2-test-")
    src = os.path.join(work, "source")
    repo = os.path.join(work, "repo")
    dest = os.path.join(work, "dest")
    try:
        os.makedirs(repo)
        subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
        os.makedirs(os.path.join(repo, "skills"))

        make_skill(src, "deploy-x", "bob-oracle", "git-workflows", "# deploy-x\n\nsteps A")
        make_skill(src, "scaffold-y", "jack-oracle", "scaffolding", "# scaffold-y\n\nsteps B")

        # 1. collect both into repo, organized by category, one commit
        code, js, raw = sh(sys.executable, COLLECT, "--repo", repo, "--from", src)
        check("collect committed both", js and sorted(js.get("committed", [])) == ["deploy-x", "scaffold-y"], raw)
        check("deploy-x under its category",
              os.path.isfile(os.path.join(repo, "skills", "git-workflows", "deploy-x", "SKILL.md")))
        check("scaffold-y under its category",
              os.path.isfile(os.path.join(repo, "skills", "scaffolding", "scaffold-y", "SKILL.md")))
        check("one commit made", count_commits(repo) == "1", f"commits={count_commits(repo)}")

        # 2. idempotent: same source again -> both skipped, no new commit
        code, js, raw = sh(sys.executable, COLLECT, "--repo", repo, "--from", src)
        check("re-collect skips both", js and sorted(js.get("skipped", [])) == ["deploy-x", "scaffold-y"], raw)
        check("no new commit", count_commits(repo) == "1", f"commits={count_commits(repo)}")

        # 3. name collision, different content -> rename to <name>-<created_by>
        src2 = os.path.join(work, "source2")
        make_skill(src2, "deploy-x", "bob-oracle", "git-workflows", "# deploy-x\n\nTOTALLY DIFFERENT steps")
        code, js, raw = sh(sys.executable, COLLECT, "--repo", repo, "--from", src2)
        ren = js.get("renamed", []) if js else []
        check("collision renamed", ren and ren[0]["from"] == "deploy-x" and ren[0]["to"] == "deploy-x-bob-oracle", raw)
        renmd = os.path.join(repo, "skills", "git-workflows", "deploy-x-bob-oracle", "SKILL.md")
        check("renamed skill written", os.path.isfile(renmd))
        check("renamed frontmatter name fixed",
              os.path.isfile(renmd) and "name: deploy-x-bob-oracle" in open(renmd).read())

        # 4. sync -> dest, FLATTENED (no category dirs), all three present
        code, js, raw = sh(sys.executable, SYNC, "--repo", repo, "--dest", dest)
        check("sync flattens deploy-x", os.path.isfile(os.path.join(dest, "deploy-x", "SKILL.md")), raw)
        check("sync flattens scaffold-y", os.path.isfile(os.path.join(dest, "scaffold-y", "SKILL.md")))
        check("sync flattens renamed", os.path.isfile(os.path.join(dest, "deploy-x-bob-oracle", "SKILL.md")))
        check("no category dirs in dest", not os.path.isdir(os.path.join(dest, "git-workflows")))

        # 5. sync idempotent (no crash, still there)
        code, js, raw = sh(sys.executable, SYNC, "--repo", repo, "--dest", dest)
        check("re-sync ok", js and "scaffold-y" in js.get("synced", []), raw)

        # 6. remove a skill from repo -> re-sync archives it in dest
        shutil.rmtree(os.path.join(repo, "skills", "scaffolding", "scaffold-y"))
        code, js, raw = sh(sys.executable, SYNC, "--repo", repo, "--dest", dest)
        check("removed skill archived", js and "scaffold-y" in js.get("archived", []), raw)
        check("archived out of dest top-level", not os.path.isdir(os.path.join(dest, "scaffold-y")))
        check("archived into trash", os.path.isdir(os.path.join(dest, ".auto-skill-trash", "scaffold-y")))
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{_p} passed, {_f} failed")
    sys.exit(1 if _f else 0)


if __name__ == "__main__":
    main()
