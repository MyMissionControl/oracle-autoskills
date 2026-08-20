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
import re
import shutil
import sys


# ⛔ `name:` comes from a SKILL.md this tool does not own, and it is joined into a
#   path that is then `rmtree`d. os.path.join has two teeth: a `..` segment walks
#   out of <dest>, and an ABSOLUTE segment throws the prefix away entirely
#   (join("/a/skills", "/home/me/.claude") == "/home/me/.claude"), so one bad
#   frontmatter line = rm -rf of a real directory. auto_skill.py validates what IT
#   writes, but `installer: auto-skill` is just a line of text that a hand-written,
#   uploaded or patched skill can carry too — and ~/.claude/skills really does hold
#   names like `Word / DOCX` today. So the check belongs HERE, at the delete.
_SEGMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _bad_segment(v):
    """Why `v` cannot be used as ONE directory name, or None when it can."""
    if not v or v in (".", ".."):
        return "empty or a dot segment"
    if os.path.isabs(v) or "/" in v or "\\" in v or "\x00" in v:
        return "contains a path separator (join would leave the root)"
    if not _SEGMENT_RE.match(v):
        return "not [A-Za-z0-9._-], 1-64 chars"
    return None


def _inside(root, path):
    """Belt-and-braces after the regex: a symlinked parent can still redirect a
    name that looks perfectly clean, and realpath is what sees that."""
    r, q = os.path.realpath(root), os.path.realpath(path)
    return q == r or q.startswith(r + os.sep)


def _unquote(v):
    """Strip a YAML single/double-quoted scalar — auto_skill.py emits free-text
    frontmatter values quoted, so a reader that skips this keeps the quotes."""
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

    repo_names, synced, rejected = set(), [], []
    for name, path, _ in _skill_dirs(repo_skills):
        why = _bad_segment(name)
        d = os.path.join(a.dest, name)  # FLATTEN — name only, drop category path
        if why is None and not _inside(a.dest, d):
            why = "destination resolves outside --dest"
        if why:
            # Skip it and SAY SO. Silently dropping the skill would look identical
            # to "synced fine" in the log, which is the failure this tool already
            # got bitten by once (see collect_commit's add/commit rc comment).
            rejected.append({"name": name, "dir": path, "reason": why})
            print(f"sync_skills: refused {name!r} from {path} — {why}", file=sys.stderr)
            continue
        repo_names.add(name)
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

    out = {"synced": synced, "archived": archived, "dest": a.dest}
    if rejected:
        out["rejected"] = rejected
    print(json.dumps(out))


if __name__ == "__main__":
    main()
