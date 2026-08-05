#!/usr/bin/env python3
"""collect_commit.py — the single-committer step of oracle-skills (v2).

ONE actor (the orchestrator) runs this. It gathers auto-created skills from a
source location, places them into the central repo's skills/ (organized by their
`category:` frontmatter), dedups, then makes ONE git commit. Because only one
actor commits, there is no concurrent-writer / index-lock problem — which is why
we do NOT need per-oracle branches or per-skill merges.

Dedup policy (matches the design):
  - identical (same name + same content_hash)      -> skip (idempotent)
  - same name, DIFFERENT content                   -> rename to <name>-<created_by>
  - new name                                       -> place under skills/<category>/

Push is separate and off unless --push. mode=local pushes HEAD directly;
mode=online pushes a branch (PR creation is left to the orchestrator / a TODO).

Usage:
  collect_commit.py --repo <oracle-skills> --from <source-dir> [--mode local|online]
                    [--push] [--committer <id>]
"""
import argparse
import json
import os
import shutil
import subprocess
import sys


def _unquote(v):
    """Strip a YAML single/double-quoted scalar. auto_skill.py emits free-text
    values quoted (a description containing ': ' is otherwise invalid YAML), so a
    reader that skips this would hand back a value with the quotes still on — and
    `category` here becomes a directory name."""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        quote, inner = v[0], v[1:-1]
        return inner.replace("''", "'") if quote == "'" else inner
    return v


def _fm(text):
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = {}
    for line in parts[1].splitlines():
        if not line.strip() or line.lstrip() != line:
            continue  # top-level keys only; skip nested-block lines
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = _unquote(v.strip())
    return fm


def _identity(fm):
    """What makes two SKILL.md files the SAME skill rather than a name collision.
    Author + birth timestamp: an edit changes the content hash but never these."""
    return (fm.get("created_by", ""), fm.get("created_at", ""))


def _skill_dirs(root):
    """Yield (name, path, fm) for every */SKILL.md under root, skipping hidden dirs."""
    if not os.path.isdir(root):
        return
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if "SKILL.md" in files:
            fm = _fm(open(os.path.join(dirpath, "SKILL.md")).read())
            if fm.get("name"):
                yield fm["name"], dirpath, fm


def _git(repo, *args, committer=None):
    cmd = ["git", "-C", repo]
    if committer:
        cmd += ["-c", f"user.email={committer}@oracle", "-c", f"user.name={committer}"]
    cmd += list(args)
    return subprocess.run(cmd, capture_output=True, text=True)


def main():
    ap = argparse.ArgumentParser(prog="collect_commit")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--mode", choices=["local", "online"], default="local")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--committer", default=os.environ.get("AUTO_SKILL_COMMITTER", "oracle-skills-bot"))
    a = ap.parse_args()

    skills_root = os.path.join(a.repo, "skills")
    os.makedirs(skills_root, exist_ok=True)

    # index existing skills already in the repo: name -> (content_hash, dir, identity)
    existing = {}
    for name, path, fm in _skill_dirs(skills_root):
        existing[name] = (fm.get("content_hash", ""), path, _identity(fm))

    committed, skipped, renamed, updated = [], [], [], []
    for name, path, fm in _skill_dirs(a.src):
        if fm.get("installer") != "auto-skill":
            continue
        h = fm.get("content_hash", "")
        cat = (fm.get("category", "") or "uncategorized")
        target = name
        dest = None
        if name in existing:
            old_hash, old_path, old_ident = existing[name]
            if old_hash == h:
                skipped.append(name)
                continue
            if old_ident == _identity(fm):
                # SAME skill, edited since it was last collected -- update in place.
                # Renaming here is what ballooned this repo to 579 copies of one
                # skill: an edited skill collides with itself on every single run,
                # so each run minted <name>-<author>-<n+1> and never touched the
                # stale original, which then collided again the following week.
                dest = old_path
                updated.append(name)
            else:
                # Genuinely different skill that happens to share a name (a
                # different author's). This is the case the rename was written for.
                by = fm.get("created_by", "x") or "x"
                target = f"{name}-{by}"
                n = 2
                while target in existing:
                    target = f"{name}-{by}-{n}"
                    n += 1
                renamed.append({"from": name, "to": target})
        if dest is None:
            dest = os.path.join(skills_root, cat, target)
        if os.path.exists(dest):
            shutil.rmtree(dest)
        shutil.copytree(path, dest)
        if target != name:  # keep frontmatter name in sync with the renamed folder
            dmd = os.path.join(dest, "SKILL.md")
            txt = open(dmd).read().replace(f"name: {name}", f"name: {target}", 1)
            open(dmd, "w").write(txt)
        existing[target] = (h, dest, _identity(fm))
        if target not in [u for u in updated]:
            committed.append(target)

    commit_sha = None
    pushed = None  # None = not attempted; True/False = attempted, did it land
    if committed or renamed or updated:
        _git(a.repo, "add", "-A")
        msg = f"auto-skill: +{len(committed)} skill(s)"
        if updated:
            msg += f", {len(updated)} updated in place"
        if renamed:
            msg += f", {len(renamed)} renamed on name-collision"
        _git(a.repo, "commit", "-m", msg, committer=a.committer)
        rev = _git(a.repo, "rev-parse", "HEAD")
        commit_sha = rev.stdout.strip() if rev.returncode == 0 else None
        if a.push:
            if a.mode == "local":
                push_res = _git(a.repo, "push", "origin", "HEAD")
            else:  # online: push a batch branch; PR creation left to the orchestrator
                push_res = _git(a.repo, "push", "origin", "HEAD:auto-skill/batch")
            pushed = push_res.returncode == 0
            if not pushed:
                print(json.dumps({"error": "push_failed", "stderr": push_res.stderr.strip(),
                                  "commit": commit_sha}), file=sys.stderr)

    print(json.dumps({"committed": committed, "updated": updated, "skipped": skipped,
                      "renamed": renamed, "commit": commit_sha, "pushed": pushed, "mode": a.mode}))


if __name__ == "__main__":
    main()
