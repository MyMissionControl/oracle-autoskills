#!/usr/bin/env python3
"""janitor — name the COLD auto-skills so their descriptions can be suppressed.

Keeps Claude Code's eager skill listing bounded: an auto-skill that is never
invoked natively still costs always-on context every session.

It used to do that by MOVING the skill to ~/.claude/skills-lib, a directory the
CLI does not scan. That was a workaround from before Claude Code had
`skillOverrides`, and it was strictly worse than the setting in every way:

  * a moved skill can no longer be invoked with the Skill tool, and the human
    can no longer type /name for it — the CLI does not know it exists;
  * the move was a one-way trapdoor. Coldness is measured from Skill-tool
    invocations, which a moved skill can never accumulate, so it could never
    come back on its own;
  * measured on this machine, 8 of the 9 skills ever moved were untouched by
    anything for the following 17 days. Hidden turned out to mean dead.

`skillOverrides: {"<name>": "name-only"}` gets the same tokens back — the
description leaves the listing — while the file stays where it is, still
Skill-invocable, still typeable, still indexed and searchable by skills-mcp.
This is also what the spec's BUILD stage does with `config.disabled`: one
directory, a config list, no file movement.

So the janitor no longer moves anything. It reports which skills are cold and,
with --apply, writes them into skillOverrides.

A skill is COLD (suppressible) only if ALL hold:
  - frontmatter has `installer: auto-skill` (machine-generated; never touch
    hand-authored oracle skills or symlinked skills)
  - it is a real directory, not a symlink
  - 0 native Skill-tool invocations across the transcripts
    (pattern "skill":"<name>" — the Skill() tool input)
  - older than --min-age-days (default 7) so brand-new skills aren't swept
    before they've had a chance to be used

DRY-RUN by default; --apply edits ~/.claude/settings.json. Reversal is deleting
the entry: nothing on disk was touched. The write is guarded (backup, value
enum-checked, staged through a temp file, atomic replace) because one bad value
makes Claude Code discard the ENTIRE settings file, permissions and all.

Usage:
  python3 janitor.py                     # dry-run: list the cold skills
  python3 janitor.py --apply             # write them into skillOverrides
  python3 janitor.py --min-age-days 14 --apply
  python3 janitor.py --state user-invocable-only --apply
"""

import argparse
import datetime
import glob
import json
import os
import re
import shutil
import sys

SRC = os.path.expanduser(os.environ.get("SKILLS_JANITOR_SRC", "~/.claude/skills"))
SETTINGS = os.path.expanduser(os.environ.get("SKILLS_JANITOR_SETTINGS",
                                             "~/.claude/settings.json"))
TRANSCRIPTS = os.path.expanduser("~/.claude/projects")

# The states Claude Code accepts. "name-only" is the one that fits: the model
# still sees the skill exists and can still invoke it, it just stops paying for
# the description every call.
STATES = ("on", "name-only", "user-invocable-only", "off")


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


def _write_overrides(names, state):
    """Merge {name: state} into settings.json. Guarded, because Claude Code
    silently discards the WHOLE file if any value is not in the enum — taking
    permissions, hooks and model with it."""
    if state not in STATES:
        raise SystemExit(f"refusing: {state!r} is not one of {STATES}")
    with open(SETTINGS, encoding="utf-8") as f:
        data = json.load(f)
    before = {k: (len(v) if isinstance(v, (list, dict)) else v) for k, v in data.items()}

    stamp = datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H-%M-%S")
    backup = f"{SETTINGS}.backup-{stamp}"
    shutil.copyfile(SETTINGS, backup)

    overrides = dict(data.get("skillOverrides") or {})
    added = [n for n in names if overrides.get(n) != state]
    overrides.update({n: state for n in names})
    if any(v not in STATES for v in overrides.values()):
        raise SystemExit("refusing: existing skillOverrides holds a value outside the enum")
    data["skillOverrides"] = overrides

    tmp = SETTINGS + ".janitor-new"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    with open(tmp, encoding="utf-8") as f:      # parse before it becomes the real file
        json.load(f)
    os.replace(tmp, SETTINGS)

    with open(SETTINGS, encoding="utf-8") as f:
        after = json.load(f)
    lost = [k for k, v in before.items()
            if k != "skillOverrides"
            and (len(after[k]) if isinstance(after.get(k), (list, dict)) else after.get(k)) != v]
    if lost:                                    # put it back rather than leave it damaged
        shutil.copyfile(backup, SETTINGS)
        raise SystemExit(f"refusing: keys would have changed {lost}; restored from {backup}")
    return added, backup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="write the cold skills into skillOverrides (default: dry-run)")
    ap.add_argument("--min-age-days", type=float, default=7.0,
                    help="only consider skills older than this (default 7)")
    ap.add_argument("--state", default="name-only", choices=list(STATES),
                    help="what to set cold skills to (default name-only)")
    a = ap.parse_args()

    now = datetime.datetime.now().astimezone()
    invoked = _invoked_skill_names()

    cold, kept_invoked, kept_new = [], [], []
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
            cold.append(fm.get("name") or name)

    print(f"skills dir: {SRC}")
    print(f"settings  : {SETTINGS}")
    print(f"min-age-days: {a.min_age_days}   state: {a.state}   "
          f"mode: {'APPLY' if a.apply else 'DRY-RUN'}")
    print("-" * 60)
    if kept_invoked:
        print("KEEP (invoked natively):")
        for n, c in sorted(kept_invoked, key=lambda x: -x[1]):
            print(f"  {c:>3}x  {n}")
    if kept_new:
        print("KEEP (too new):")
        for n, ag in kept_new:
            print(f"  {ag:4.1f}d  {n}")
    verb = "would set" if not a.apply else "setting"
    print(f"\nCOLD -> {verb} {a.state} ({len(cold)}):")
    for n in cold:
        print(f"  {n}")
    if not cold:
        print("  (none)")

    if a.apply and cold:
        added, backup = _write_overrides(cold, a.state)
        print(f"\nWROTE {len(added)} new override(s) to {SETTINGS}")
        print(f"  backup: {backup}")
        print("  nothing on disk moved — every skill is still Skill-invocable,")
        print("  still typeable as /name, and still indexed by skills-mcp.")
        print("RELOAD the Claude Code window so the eager listing shrinks.")
    elif not a.apply and cold:
        print(f"\n(dry-run — re-run with --apply to write them into skillOverrides)")


if __name__ == "__main__":
    main()
