#!/usr/bin/env python3
"""sync_skills.py — make the central catalog live for an oracle (v2).

Copies repo/skills/**/<name>/ into <dest>/<name>/ , FLATTENED: the category
directories are dropped so Claude Code discovers the skills regardless of whether
it scans nested folders. The repo is the source of truth (dest copies are
overwritten). Non-destructive the other way: a <dest> skill stamped
installer:auto-skill that is no longer in the repo is archived to
<dest>/.auto-skill-trash/ (Nothing is Deleted), never hard-removed.

Usage:
  sync_skills.py --repo <oracle-skills> [--dest <skills-dir, default ~/.claude/skills>]
"""
import argparse
import json
import os
import shutil


def _fm(text):
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    fm = {}
    for line in parts[1].splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm


def _skill_dirs(root):
    if not os.path.isdir(root):
        return
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        if "SKILL.md" in files:
            fm = _fm(open(os.path.join(dirpath, "SKILL.md")).read())
            if fm.get("name"):
                yield fm["name"], dirpath, fm


def main():
    ap = argparse.ArgumentParser(prog="sync_skills")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dest", default=os.path.expanduser("~/.claude/skills"))
    a = ap.parse_args()

    os.makedirs(a.dest, exist_ok=True)
    repo_skills = os.path.join(a.repo, "skills")

    repo_names, synced = set(), []
    for name, path, _ in _skill_dirs(repo_skills):
        repo_names.add(name)
        d = os.path.join(a.dest, name)  # FLATTEN — name only, drop category path
        if os.path.exists(d):
            shutil.rmtree(d)
        shutil.copytree(path, d)
        synced.append(name)

    # archive auto-skill skills in dest that the repo no longer has
    archived = []
    for entry in sorted(os.listdir(a.dest)):
        if entry.startswith("."):
            continue
        md = os.path.join(a.dest, entry, "SKILL.md")
        if not os.path.isfile(md):
            continue
        fm = _fm(open(md).read())
        nm = fm.get("name", entry)
        if fm.get("installer") == "auto-skill" and nm not in repo_names and entry not in repo_names:
            trash = os.path.join(a.dest, ".auto-skill-trash")
            os.makedirs(trash, exist_ok=True)
            tgt = os.path.join(trash, entry)
            if os.path.exists(tgt):
                shutil.rmtree(tgt)
            shutil.move(os.path.join(a.dest, entry), tgt)
            archived.append(entry)

    print(json.dumps({"synced": synced, "archived": archived, "dest": a.dest}))


if __name__ == "__main__":
    main()
