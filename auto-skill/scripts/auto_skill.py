#!/usr/bin/env python3
"""auto_skill.py — non-blocking writer for auto-created Claude Code skills.

This is the deterministic, testable half of soulbrew's Hermes-style
auto-skill-creation ("mechanism C"). An agent that self-judges one of the
autonomous triggers (see the "Skill Discipline" block in CLAUDE.md) calls this
instead of a blocking /command, so it works in unattended worker panes too.

Design points it enforces (from the feasibility review):
  - NON-BLOCKING: pure CLI, prints one JSON line, never asks a question.
  - NO SILENT CLOBBER: a name clash with *different* content is REFUSED
    (exit 2) unless --force. Same content is idempotent (exists-identical).
  - LANDS GLOBAL BY DEFAULT: writes under ~/.claude/skills so the skill shows in
    the Mission Control Skills panel and is usable in every project. --dir /
    $AUTO_SKILL_DIR override. Same-name/different-content is refused (no clobber).
  - PROVENANCE: every write is stamped installer: auto-skill + created_at +
    trigger, so it is filterable and janitor-able later.
  - STAGE MODE: --stage parks the write in .pending-skills/ for review
    (the write-approval gate, mechanism E) instead of going live.

Commands:
  create --name <slug> --desc <text> [--body <s> | --body-file <p>]
         [--dir <skills_dir>] [--global] [--stage] [--force]
         [--trigger <label>] [--source <id>]
  validate <path-to-SKILL.md>
  list [--dir <skills_dir>] [--global]
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,48}$")
CAT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,32}$")  # optional single category segment
MAX_DESC = 200
INSTALLER = "auto-skill"
VALID_TRIGGERS = {
    "complex-task", "error-recovery", "user-correction",
    "reusable-workflow", "manual", "",
}


def _emit(obj, ok=True):
    """Print a single JSON line and exit (0 if ok else 2)."""
    print(json.dumps(obj))
    sys.exit(0 if ok else 2)


def _now_iso():
    # local time with tz offset; falls back to naive if tz unavailable
    try:
        return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    except Exception:
        return datetime.datetime.now().replace(microsecond=0).isoformat()


def _body_hash(body):
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()


# Report-only near-duplicate detection. The name clash guard below catches
# `create --name x` twice; it cannot catch the same procedure arriving under a
# second name, which is how the catalog actually grows -- measured at 8.9 skills
# a week, with `orches-backend-sprint-completion` and its `-frontend-` twin
# sharing 73% of their vocabulary.
#
# This only ever ADDS a `near_duplicates` field to the emitted JSON. It must not
# be able to refuse a write or raise: a capture lost to a false positive costs
# more than a duplicate skill, so every failure path here returns "no opinion".
DUP_THRESHOLD = 0.40  # overlap of the smaller token set; catalog p99 is 0.32
DUP_STOPWORDS = frozenset(
    "use when the a an and or to of for in on with this that it is are be as by "
    "from at not do into if then than so".split())


def _dup_tokens(text):
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) > 2 and w not in DUP_STOPWORDS}


def _near_duplicates(skills_dir, name, desc, limit=3):
    """Existing skills whose name+description vocabulary overlaps this one."""
    try:
        threshold = float(os.environ.get("AUTO_SKILL_DUP_THRESHOLD") or DUP_THRESHOLD)
    except ValueError:
        threshold = DUP_THRESHOLD
    if threshold <= 0:
        return []
    mine = _dup_tokens(name.replace("-", " ") + " " + desc)
    if not mine:
        return []
    hits = []
    try:
        entries = sorted(os.listdir(skills_dir))
    except OSError:
        return []
    for other in entries:
        if other == name or other.startswith("."):
            continue
        path = os.path.join(skills_dir, other, "SKILL.md")
        try:
            with open(path, errors="replace") as fh:
                head = fh.read(2500)
        except OSError:
            continue
        m = re.search(r"^description:\s*(.+)$", head, re.M)
        theirs = _dup_tokens(other.replace("-", " ") + " " +
                             (m.group(1).strip().strip("\"'") if m else ""))
        if not theirs:
            continue
        overlap = len(mine & theirs) / min(len(mine), len(theirs))
        if overlap >= threshold:
            hits.append({"name": other, "overlap": round(overlap, 2)})
    hits.sort(key=lambda h: -h["overlap"])
    return hits[:limit]


def _default_dir(use_global):
    # GLOBAL-ONLY landing: default to ~/.claude/skills so auto-created skills show
    # in the Mission Control Skills panel (it scans ~/.claude/skills) and are usable
    # in every project. --dir and $AUTO_SKILL_DIR still override for special cases.
    home_skills = os.path.join(os.path.expanduser("~"), ".claude", "skills")
    if use_global:
        return home_skills
    env = os.environ.get("AUTO_SKILL_DIR")
    if env:
        return env
    return home_skills


def _yaml_scalar(v):
    """Render a value as a single-line, always-single-quoted YAML scalar.

    Descriptions here routinely read "Use when <trigger>: <behavior>", and an
    unquoted value containing ': ' is INVALID YAML — a strict parser then fails
    and every reader falls back to naive line splitting, which silently drops all
    nested blocks (requires:, triggers:) in that file. Measured 2026-08-03: 18 of
    50 generated skills (36%) were invalid this way. Quoting unconditionally
    keeps output predictable instead of depending on which characters appear."""
    s = "" if v is None else str(v).replace("\n", " ").replace("\r", " ").strip()
    return "'" + s.replace("'", "''") + "'"


def _unquote(v):
    """Inverse of _yaml_scalar for the flat reader below."""
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        quote, inner = v[0], v[1:-1]
        return inner.replace("''", "'") if quote == "'" else inner
    return v


def _read_frontmatter(text):
    """Return (dict, body) from a SKILL.md string. Missing block -> ({}, text).
    Flat: top-level keys only, so an indented line belonging to a nested block is
    skipped rather than mistaken for a key of its own."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    fm_raw, body = parts[1], parts[2]
    fm = {}
    for line in fm_raw.splitlines():
        if not line.strip() or line.lstrip() != line:
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = _unquote(v.strip())
    return fm, body.lstrip("\n")


def _render(name, desc, body, trigger, source, category):
    """Assemble a stamped SKILL.md string. content_hash covers the body only."""
    body = body.strip() or f"# /{name}\n\n{desc}\n\n## Steps\n\n1. <fill in the procedure>\n"
    fm = [
        "---",
        f"name: {name}",
        f"description: {_yaml_scalar(desc)}",
        f"installer: {INSTALLER}",
        f"created_at: {_now_iso()}",
        f"created_session: {(os.environ.get('CLAUDE_SESSION_ID') or '')[:8]}",
        f"trigger: {_yaml_scalar(trigger)}",
        f"created_by: {_yaml_scalar(source)}",
        f"category: {_yaml_scalar(category)}",
        f"content_hash: {_body_hash(body)}",
        "---",
        "",
    ]
    return "\n".join(fm) + body.rstrip() + "\n"


def _kebab(s):
    """Coerce a name/category to the kebab shape NAME_RE/CAT_RE demand."""
    # Every non-alphanumeric run becomes a single separator, so 'Bad Cat/x' is
    # 'bad-cat-x' and not 'bad-catx' — deleting a separator silently welds two
    # words together, which reads as a different name.
    s = re.sub(r"[^a-z0-9]+", "-", str(s or "").strip().lower())
    return s.strip("-")


def _fit_desc(desc):
    """Collapse whitespace and, if still over MAX_DESC, cut at a word boundary.

    Returns (desc, original_len or None). This used to exit 2 instead: measured
    2026-08-11 over the real transcripts, 133 create calls produced 42 refusals
    (32%), 49 of them 'description too long' — every one a wasted turn at the end
    of a task where the caller is told the capture must be non-blocking. The cap
    is also stricter than the catalog it writes into (37 of 118 live skills carry
    longer descriptions), so agents write in a style this writer refused. Truncate
    and REPORT it instead: a slightly clipped description still fires, a refused
    write saves nothing at all."""
    d = re.sub(r"\s+", " ", str(desc or "")).strip()
    if len(d) <= MAX_DESC:
        return d, None
    orig = len(d)
    cut = d[:MAX_DESC - 1]
    sp = cut.rfind(" ")
    if sp > MAX_DESC * 0.6:  # keep a word boundary unless that loses too much
        cut = cut[:sp]
    return cut.rstrip(" ,;:.-") + "…", orig


def cmd_create(a):
    # Repair inputs rather than bouncing them; record what changed so the caller
    # sees it in the JSON instead of guessing why the text differs on disk.
    repairs = {}
    name_given = (a.name or "").strip()
    name = _kebab(name_given)
    if name != name_given:
        repairs["name"] = {"given": name_given, "used": name}
    desc, desc_orig = _fit_desc(a.desc)
    if desc_orig:
        repairs["description"] = {"given_chars": desc_orig, "max": MAX_DESC,
                                  "used": desc}
    trig_given = (a.trigger or "").strip()
    a.trigger = re.sub(r"[\s_]+", "-", trig_given.lower())
    if a.trigger != trig_given:
        repairs["trigger"] = {"given": trig_given, "used": a.trigger}

    if not NAME_RE.match(name):
        _emit({"status": "invalid", "name": name, "given_name": name_given,
               "message": "name must be kebab-case ^[a-z0-9][a-z0-9-]{1,48}$ "
                          f"(normalized {name_given!r} to {name!r}, still invalid)"}, ok=False)
    if not desc:
        _emit({"status": "invalid", "name": name,
               "message": "description is required"}, ok=False)
    if a.trigger not in VALID_TRIGGERS:
        _emit({"status": "invalid", "name": name,
               "message": f"trigger must be one of {sorted(VALID_TRIGGERS)} "
                          f"(normalized {trig_given!r} to {a.trigger!r})"}, ok=False)

    # WHO created it is mandatory — from --source or $AUTO_SKILL_SOURCE (the
    # oracle's id). Refuse rather than write an anonymous skill.
    source = (a.source or os.environ.get("AUTO_SKILL_SOURCE") or "").strip()
    if not source:
        _emit({"status": "invalid", "name": name,
               "message": "creator id required — pass --source <oracle-id> or set AUTO_SKILL_SOURCE"}, ok=False)

    cat_given = (a.category or "").strip()
    category = _kebab(cat_given)
    if category != cat_given:
        repairs["category"] = {"given": cat_given, "used": category}
    if category and not CAT_RE.match(category):
        _emit({"status": "invalid", "name": name,
               "message": "category must be a single kebab segment ^[a-z0-9][a-z0-9-]{0,32}$"}, ok=False)

    body = a.body or ""
    if a.body_file:
        try:
            body = open(a.body_file).read()
        except OSError as e:
            _emit({"status": "invalid", "name": name, "message": str(e)}, ok=False)

    skills_dir = a.dir or _default_dir(a.g)
    rendered = _render(name, desc, body, a.trigger, source, category)
    new_hash = _body_hash((body.strip() or f"# /{name}\n\n{desc}\n\n## Steps\n\n1. <fill in the procedure>\n"))

    # Computed before the write so it cannot see the skill being created, and
    # reported rather than enforced -- see _near_duplicates.
    dups = _near_duplicates(skills_dir, name, desc)

    def _note(payload):
        if repairs:
            payload["repaired"] = repairs
            payload["message"] += "; repaired input: " + ", ".join(sorted(repairs))
        if dups:
            payload["near_duplicates"] = dups
            payload["message"] += ("; overlaps existing " +
                                   ", ".join(f"{d['name']} ({d['overlap']})" for d in dups) +
                                   " — consider editing that one instead")
        return payload

    if a.stage:
        dest_dir = os.path.join(skills_dir, ".pending-skills", name)
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, "SKILL.md")
        queue = os.path.join(skills_dir, ".pending-skills", "queue.md")

        def _log_queue():
            # append-only ledger; each line is far under PIPE_BUF, so concurrent
            # workers' appends stay atomic and none is lost.
            with open(queue, "a") as f:
                f.write(f"- {_now_iso()}  {name}  ({a.trigger or 'n/a'})  {desc}\n")

        # ATOMIC, same first-writer-wins rule as the live create path below: two
        # workers staging the same name at once can't clobber each other inside
        # .pending-skills/. Exclusive create ("x") picks one winner; everyone else
        # gets FileExistsError and reconciles (identical / refuse / force).
        try:
            with open(dest, "x") as f:
                f.write(rendered)
            _log_queue()
            _emit(_note({"status": "staged", "name": name, "path": dest,
                         "message": "staged for review; approve to go live"}))
        except FileExistsError:
            pass  # already staged (pre-existing, or we lost the race) -> reconcile

        existing_fm, _ = _read_frontmatter(open(dest).read())
        if existing_fm.get("content_hash") == new_hash:
            _emit({"status": "exists-identical", "name": name, "path": dest,
                   "message": "identical skill already staged; nothing to do"})
        if not a.force:
            _emit({"status": "refused-conflict", "name": name, "path": dest,
                   "message": "a different skill with this name is already staged; "
                              "use --force or choose another name (no silent overwrite)"}, ok=False)
        with open(dest, "w") as f:
            f.write(rendered)
        _log_queue()
        _emit(_note({"status": "staged", "name": name, "path": dest,
                     "message": "staged for review; approve to go live"}))

    dest_dir = os.path.join(skills_dir, name)
    dest = os.path.join(dest_dir, "SKILL.md")
    os.makedirs(dest_dir, exist_ok=True)

    # ATOMIC first-writer-wins. Two oracles creating the same name at the same
    # instant used to both pass an os.path.exists() check and then clobber each
    # other with open("w") — the loser's skill vanished silently. Exclusive
    # create ("x") closes that TOCTOU race at the OS level: exactly one process
    # creates the file; everyone else gets FileExistsError and falls through to
    # the SAME identical / refuse / force reconciliation as a pre-existing file.
    # So a concurrent name clash with different content is REFUSED, never
    # silently overwritten.
    try:
        with open(dest, "x") as f:
            f.write(rendered)
        _emit(_note({"status": "created", "name": name, "path": dest,
                     "trigger": a.trigger,
                     "message": "skill written; live immediately"}))
    except FileExistsError:
        pass  # already on disk (pre-existing, or we lost the create race) -> reconcile

    existing_fm, _ = _read_frontmatter(open(dest).read())
    if existing_fm.get("content_hash") == new_hash:
        _emit({"status": "exists-identical", "name": name, "path": dest,
               "message": "identical skill already present; nothing to do"})
    if not a.force:
        _emit({"status": "refused-conflict", "name": name, "path": dest,
               "message": "a different skill with this name exists; use --force "
                          "or choose another name (no silent overwrite)"}, ok=False)
    with open(dest, "w") as f:
        f.write(rendered)
    _emit(_note({"status": "created", "name": name, "path": dest,
                 "trigger": a.trigger,
                 "message": "skill written; live immediately"}))


def cmd_validate(a):
    path = a.path
    errors = []
    try:
        text = open(path).read()
    except OSError as e:
        _emit({"valid": False, "path": path, "errors": [str(e)]}, ok=False)
    fm, body = _read_frontmatter(text)
    if not fm:
        errors.append("no YAML frontmatter block")
    name = fm.get("name", "")
    if not name:
        errors.append("frontmatter missing 'name'")
    elif not NAME_RE.match(name):
        errors.append(f"name '{name}' is not valid kebab-case")
    if not fm.get("description"):
        errors.append("frontmatter missing 'description'")
    if not body.strip():
        errors.append("empty skill body")
    valid = not errors
    _emit({"valid": valid, "path": path, "errors": errors}, ok=valid)


def cmd_list(a):
    skills_dir = a.dir or _default_dir(a.g)
    out = []
    if os.path.isdir(skills_dir):
        for entry in sorted(os.listdir(skills_dir)):
            if entry.startswith("."):
                continue
            md = os.path.join(skills_dir, entry, "SKILL.md")
            if not os.path.isfile(md):
                continue
            fm, _ = _read_frontmatter(open(md).read())
            if fm.get("installer") == INSTALLER:
                out.append({"name": fm.get("name", entry),
                            "description": fm.get("description", ""),
                            "created_at": fm.get("created_at", ""),
                            "trigger": fm.get("trigger", ""),
                            "category": fm.get("category", ""),
                            "created_by": fm.get("created_by", ""),
                            "path": md})
    print(json.dumps(out))
    sys.exit(0)


def build_parser():
    p = argparse.ArgumentParser(prog="auto_skill")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("create")
    c.add_argument("--name", required=True)
    c.add_argument("--desc", required=True)
    c.add_argument("--body", default="")
    c.add_argument("--body-file", dest="body_file", default="")
    c.add_argument("--dir", default="")
    c.add_argument("--global", dest="g", action="store_true")
    c.add_argument("--stage", action="store_true")
    c.add_argument("--force", action="store_true")
    c.add_argument("--trigger", default="")
    c.add_argument("--source", default="")
    c.add_argument("--category", default="")
    c.set_defaults(fn=cmd_create)

    v = sub.add_parser("validate")
    v.add_argument("path")
    v.set_defaults(fn=cmd_validate)

    l = sub.add_parser("list")
    l.add_argument("--dir", default="")
    l.add_argument("--global", dest="g", action="store_true")
    l.set_defaults(fn=cmd_list)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    args.fn(args)
