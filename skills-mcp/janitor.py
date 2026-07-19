#!/usr/bin/env python3
"""janitor — sweep COLD auto-skills into the lazy skills-lib dir.

Keeps Claude Code's eager skill listing bounded: an auto-skill that is never
invoked natively still costs always-on context every session. This finds the
cold ones and moves them to ~/.claude/skills-lib (served on demand by skills-mcp
via skills_list/skill_view) instead of the eager ~/.claude/skills.

A skill is COLD (movable) only if ALL hold:
  - frontmatter has `installer: auto-skill` (machine-generated; never touch
    hand-authored oracle skills or symlinked skills)
  - it is a real directory, not a symlink
  - 0 native Skill-tool invocations across the transcripts
    (pattern "skill":"<name>" — the Skill() tool input)
  - older than --min-age-days (default 7) so brand-new skills aren't swept
    before they've had a chance to be used

Mirrors Hermes' 'curator' prune pass (minus consolidation). DRY-RUN by default;
pass --apply to actually move. Reversal: entries are appended to
<lib>/.migrated-from-skills.txt; `mv` them back to restore.

Usage:
  python3 janitor.py                 # dry-run: show what would move
  python3 janitor.py --apply         # move the cold ones
  python3 janitor.py --min-age-days 14 --apply
"""

import argparse
import datetime
import glob
import os
import re
import shutil
import sys

SRC = os.path.expanduser(os.environ.get("SKILLS_JANITOR_SRC", "~/.claude/skills"))
LIB = os.path.expanduser(os.environ.get("SKILLS_JANITOR_LIB", "~/.claude/skills-lib"))
TRANSCRIPTS = os.path.expanduser("~/.claude/projects")


def _frontmatter(md_path):
    """Minimal top-level key: value parse (name/installer/created_at)."""
    fm = {}
    try:
        with open(md_path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        return fm
    if not text.startswith("---"):
        return fm
    lines = text.splitlines()
    for ln in lines[1:]:
        if ln.strip() == "---":
            break
        if ln.lstrip() != ln or ":" not in ln:
            continue
        k, _, v = ln.partition(":")
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        fm[k.strip()] = v
    return fm


def _invoked_skill_names():
    """One pass over all transcripts -> set of skills invoked via the Skill tool."""
    pat = re.compile(r'"skill"\s*:\s*"([^"]+)"')
    invoked = {}
    for path in glob.glob(os.path.join(TRANSCRIPTS, "**", "*.jsonl"), recursive=True):
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"skill"' not in line:
                        continue
                    for m in pat.findall(line):
                        invoked[m] = invoked.get(m, 0) + 1
        except OSError:
            continue
    return invoked


def _age_days(created_at, now):
    if not created_at:
        return None
    try:
        dt = datetime.datetime.fromisoformat(created_at)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=now.tzinfo)
        return (now - dt).total_seconds() / 86400.0
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="actually move (default: dry-run)")
    ap.add_argument("--min-age-days", type=float, default=7.0,
                    help="only sweep skills older than this (default 7)")
    a = ap.parse_args()

    now = datetime.datetime.now().astimezone()
    invoked = _invoked_skill_names()

    move, kept_invoked, kept_new, skipped = [], [], [], []
    for md in sorted(glob.glob(os.path.join(SRC, "*", "SKILL.md"))):
        d = os.path.dirname(md)
        name = os.path.basename(d)
        if os.path.islink(d):
            continue
        fm = _frontmatter(md)
        if fm.get("installer") != "auto-skill":
            continue
        inv = invoked.get(fm.get("name") or name, 0)
        age = _age_days(fm.get("created_at"), now)
        if inv > 0:
            kept_invoked.append((name, inv))
        elif age is not None and age < a.min_age_days:
            kept_new.append((name, age))
        else:
            move.append(name)

    print(f"src (eager): {SRC}")
    print(f"lib (lazy):  {LIB}")
    print(f"min-age-days: {a.min_age_days}   mode: {'APPLY' if a.apply else 'DRY-RUN'}")
    print("-" * 60)
    if kept_invoked:
        print("KEEP (invoked natively):")
        for n, c in sorted(kept_invoked, key=lambda x: -x[1]):
            print(f"  {c:>3}x  {n}")
    if kept_new:
        print("KEEP (too new):")
        for n, ag in kept_new:
            print(f"  {ag:4.1f}d  {n}")
    print(f"\nCOLD -> would move ({len(move)}):" if not a.apply else f"\nCOLD -> moving ({len(move)}):")
    for n in move:
        print(f"  {n}")
    if not move:
        print("  (none)")

    if a.apply and move:
        os.makedirs(LIB, exist_ok=True)
        manifest = os.path.join(LIB, ".migrated-from-skills.txt")
        moved = []
        with open(manifest, "a", encoding="utf-8") as mf:
            for n in move:
                src, dst = os.path.join(SRC, n), os.path.join(LIB, n)
                if os.path.exists(dst):
                    print(f"  SKIP (exists in lib): {n}")
                    continue
                shutil.move(src, dst)
                mf.write(n + "\n")
                moved.append(n)
        print(f"\nMOVED {len(moved)} skill(s) to {LIB}")
        print("RELOAD the Claude Code window so the eager listing shrinks.")
    elif not a.apply and move:
        print("\n(dry-run — re-run with --apply to move; then reload the window)")


if __name__ == "__main__":
    main()
