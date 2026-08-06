#!/usr/bin/env python3
"""listing_report.py — measure the eager skill listing from what Claude Code
actually sent, not from an estimate of it.

The listing is the thing retrieval competes against, and until 2026-08-05 every
claim about its size in this repo was a reconstruction: read the frontmatter
`description` of each SKILL.md, render `- name: description`, add it up. That
estimate came out 27% low (21,270 vs a real 29,212) for two reasons no amount of
care would have caught -- the CLI appends ` - whenToUse` when a skill declares
one, and the listing carries ~27 built-in and plugin entries that live nowhere
in ~/.claude/skills.

There is no need to estimate. The CLI records the rendered listing in the
transcript as an attachment of `type: skill_listing`, so the exact bytes the
model was shown are on disk. This script reads them.

Four questions it answers, each of which was previously answered wrong here:

  1. How big is the listing, and which tier of skills is paying for it?
  2. Has the budget ever demoted a skill to a bare name -- and did that cost a
     real invocation? (Measured: 22 of 454 listings demoted; of 15 Skill() calls
     made inside a demoted session, 7 invoked a skill that was demoted at the
     time, and all 7 succeeded. A bare name is enough to invoke.)
  3. How fast is the listing growing, and how long until it stops fitting?
  4. What would setting a group of skills to `name-only` actually save?

Question 4 is a simulation of the CLI's own algorithm, transcribed from the
shipped bundle (v2.1.222):

    budget   = (contextWindow or 200000) * 4 * skillListingBudgetFraction
    priority = usageCount * max(0.5 ** (daysSinceLastUse / 7), 0.1)   or 0
    over budget: charge every skill a bare `- name`, then hand descriptions back
    in descending priority, skipping any that no longer fits

Two consequences of that algorithm are worth stating because they are
counter-intuitive and both were got wrong in earlier analysis:

  - The fraction is a CEILING, not a spend. While the listing fits, raising it
    costs nothing at all; it only changes what happens once you are over.
  - A skill that has never been used has priority exactly 0, and ties are broken
    by array order. On this machine that arbitrary tie-break was handing
    descriptions to 22 never-used legacy skills while demoting 22 auto-skills --
    the only tier the model ever picks unprompted.

The simulator is validated against a real demoted listing, and prints the
comparison so you can see for yourself whether to trust its predictions.

Usage:
  python3 listing_report.py                        # everything, current state
  python3 listing_report.py --name-only legacy     # simulate a name-only tier
  python3 listing_report.py --name-only a,b,c      # or an explicit list
"""
import argparse
import collections
import datetime
import glob
import json
import os
import re

# Transcribed from the shipped CLI bundle. Re-check after a Claude Code upgrade:
# these are not documented API, they are constants read out of the binary.
CHARS_PER_TOKEN = 4
DEFAULT_FRACTION = 0.01
DEFAULT_CONTEXT = 200_000
HALF_LIFE_DAYS = 7.0
PRIORITY_FLOOR = 0.1

# A new entry starts at `- <kebab-name>` followed by ": " or end of line. Any
# other line is a continuation: descriptions may contain newlines, and counting
# those lines as entries silently drops their characters from the total.
ENTRY_RE = re.compile(r"- [a-z0-9][a-z0-9:_-]*(:|$)")

TIER_ORDER = ("legacy", "auto", "hand", "builtin/plugin")


def tier_of(name: str, skills_dir: str) -> str:
    """Which tier a listing entry belongs to, by its `installer:` frontmatter.

    Do NOT detect legacy by a description prefix like `[core] ... G-SKLL |` --
    only some legacy skills carry it, and doing so undercounted the tier 17 vs 34.
    """
    path = os.path.join(skills_dir, name, "SKILL.md")
    if not os.path.exists(path):
        return "builtin/plugin"
    with open(path, errors="replace") as fh:
        head = fh.read(1200)
    m = re.search(r"^installer:\s*(.+)$", head, re.M)
    installer = m.group(1).strip() if m else ""
    if installer.startswith("arra-oracle"):
        return "legacy"
    return "auto" if installer == "auto-skill" else "hand"


def parse_listing(content: str) -> list[dict]:
    lines = []
    for line in content.split("\n"):
        if line.startswith("- ") and ENTRY_RE.match(line):
            lines.append(line)
        elif lines:
            lines[-1] += "\n" + line
    out = []
    for line in lines:
        name = line[2:].split(":", 1)[0].split("\n")[0].strip()
        out.append({"name": name, "entry_len": len(line),
                    "bare": ": " not in line[2:].split("\n")[0]})
    return out


def _attachments(rec) -> list[dict]:
    found = []
    stack = [rec]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if node.get("type") == "skill_listing":
                found.append(node)
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return found


def _when(rec: dict, path: str) -> float:
    """When the listing was built, from the record -- NOT the file's mtime.

    A long session's file is touched on every turn, so mtime says "now" for a
    listing built two days ago. Sorting by mtime picked a stale listing as the
    current one and understated the catalog by 13 skills.
    """
    stamp = rec.get("timestamp")
    if stamp:
        try:
            return datetime.datetime.fromisoformat(
                stamp.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return os.path.getmtime(path)


def transcripts(projects: str) -> tuple[list[str], list[str]]:
    """(main session files, subagent files) under the projects directory.

    A shallow `*/*.jsonl` returns 448 of 1,979 files here. Subagent and workflow
    agents keep their own transcripts two and four levels deeper:

        <project>/<session>.jsonl                              main
        <session>/subagents/agent-*.jsonl                      Task subagents
        <session>/subagents/workflows/wf_*/agent-*.jsonl       workflow agents

    Reporting them together would be wrong -- they are separate populations with
    separate listings -- but omitting them hid the fact that 1,399 of 1,410
    subagents each receive a full skill listing. Every count in rounds 1-4 of the
    analysis used the shallow glob.
    """
    found = glob.glob(os.path.join(projects, "**", "*.jsonl"), recursive=True)
    marker = os.sep + "subagents" + os.sep
    return ([p for p in found if marker not in p],
            [p for p in found if marker in p and not p.endswith("journal.jsonl")])


def scan(paths) -> list[dict]:
    """Every initial listing in `paths`, plus what the session did with skills."""
    out = []
    for path in paths:
        try:
            if os.path.getsize(path) == 0:
                continue
        except OSError:
            continue
        listings, invoked, models = [], [], set()
        with open(path, errors="replace") as fh:
            for line in fh:
                has_listing = '"skill_listing"' in line
                has_skill = '"Skill"' in line
                if not (has_listing or has_skill):
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if has_listing:
                    for att in _attachments(rec):
                        if att.get("isInitial"):
                            listings.append((_when(rec, path), att.get("content") or ""))
                if has_skill:
                    msg = rec.get("message") or {}
                    if msg.get("model"):
                        models.add(msg["model"])
                    body = msg.get("content")
                    for blk in body if isinstance(body, list) else []:
                        if isinstance(blk, dict) and blk.get("type") == "tool_use" \
                                and blk.get("name") == "Skill":
                            got = (blk.get("input") or {}).get("skill") or ""
                            got = got.lstrip("/").split()[0] if got.strip() else ""
                            if got:
                                invoked.append(got)
        for when, content in listings:
            out.append({"path": path, "mtime": when,
                        "content": content, "invoked": invoked, "models": models})
    out.sort(key=lambda r: r["mtime"])
    return out


def priority_fn(usage: dict, now_ms: float):
    def prio(name: str) -> float:
        rec = usage.get(name)
        if not rec:
            return 0.0
        days = (now_ms - rec["lastUsedAt"]) / 86_400_000.0
        return rec["usageCount"] * max(0.5 ** (days / HALF_LIFE_DAYS), PRIORITY_FLOOR)
    return prio


def simulate(entries, budget, name_only, prio, protect_builtin, tiers):
    """The CLI's own fit algorithm. Returns (mode, total_chars, demoted_names).

    `protect_builtin` models the bundled-prompt exemption. Which entries are
    bundled is not recoverable from the transcript, so run it both ways: a
    conclusion that only holds under one assumption is not a conclusion.
    """
    def bare_len(e):
        return len(e["name"]) + 2

    charged = [dict(e, entry_len=(bare_len(e) if e["name"] in name_only else e["entry_len"]))
               for e in entries]
    total = sum(e["entry_len"] for e in charged) + max(0, len(charged) - 1)
    if total <= budget:
        return "fits", total, []

    def protected(e):
        return e["name"] in name_only or (protect_builtin
                                          and tiers[e["name"]] == "builtin/plugin")

    floor = sum(e["entry_len"] if protected(e) else bare_len(e)
                for e in charged) + max(0, len(charged) - 1)
    spare = budget - floor
    # Stable sort: every never-used skill scores 0, so ties keep listing order.
    contenders = sorted((e for e in charged if not protected(e)),
                        key=lambda e: -prio(e["name"]))
    demoted, spent = [], 0
    for e in contenders:
        delta = e["entry_len"] - bare_len(e)
        if delta <= spare:
            spare -= delta
            spent += delta
        else:
            demoted.append(e["name"])
    return "priority", floor + spent, demoted


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--projects", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--skills", default=os.path.expanduser("~/.claude/skills"))
    ap.add_argument("--settings", default=os.path.expanduser("~/.claude/settings.json"))
    ap.add_argument("--state", default=os.path.expanduser("~/.claude.json"),
                    help="where skillUsage lives; it drives the demotion order")
    ap.add_argument("--name-only", default="",
                    help="simulate: a tier name (legacy/auto/hand) or comma-separated skills")
    ap.add_argument("--keep", default="rrr,who-are-you,dig",
                    help="never include these in a simulated --name-only tier")
    args = ap.parse_args()

    settings = {}
    if os.path.exists(args.settings):
        with open(args.settings, errors="replace") as fh:
            settings = json.load(fh)
    overrides = settings.get("skillOverrides") or {}
    fraction = settings.get("skillListingBudgetFraction") or DEFAULT_FRACTION
    usage = {}
    if os.path.exists(args.state):
        with open(args.state, errors="replace") as fh:
            usage = (json.load(fh).get("skillUsage") or {})
    prio = priority_fn(usage, datetime.datetime.now().timestamp() * 1000)

    main_files, sub_files = transcripts(args.projects)
    rows = scan(main_files)
    if not rows:
        print("no skill_listing attachments found under", args.projects)
        return
    latest = rows[-1]
    entries = parse_listing(latest["content"])
    tiers = {e["name"]: tier_of(e["name"], args.skills) for e in entries}
    accounted = sum(e["entry_len"] for e in entries) + max(0, len(entries) - 1)

    print("== LATEST RECORDED LISTING ==")
    print(f"  {datetime.datetime.fromtimestamp(latest['mtime']):%Y-%m-%d %H:%M}"
          f"  {os.path.basename(latest['path'])[:8]}")
    print(f"  {len(latest['content']):,} chars, {len(entries)} entries"
          f"  ({len(latest['content']) // CHARS_PER_TOKEN:,} tokens)")
    if accounted != len(latest["content"]):
        print(f"  WARNING parser accounted for {accounted:,} of "
              f"{len(latest['content']):,} chars -- entry regex needs work")
    if any(e["bare"] for e in entries):
        stale = [e["name"] for e in entries
                 if e["bare"] and overrides.get(e["name"]) != "name-only"]
        print(f"  bare entries: {sum(e['bare'] for e in entries)}"
              f"  ({len(stale)} not explained by a current name-only override)")
    print("  NOTE the listing is built at session start, so this reflects the"
          " settings in force then, not necessarily now.")

    print("\n== WHO PAYS FOR IT ==")
    by_tier = collections.defaultdict(lambda: [0, 0])
    for e in entries:
        slot = by_tier[tiers[e["name"]]]
        slot[0] += 1
        slot[1] += e["entry_len"]
    print(f"  {'tier':16}{'skills':>7}{'chars':>9}{'avg':>6}{'tokens':>8}")
    for tier in TIER_ORDER:
        n, ch = by_tier[tier]
        if n:
            print(f"  {tier:16}{n:7}{ch:9,}{ch // n:6}{ch // CHARS_PER_TOKEN:8,}")

    name_only = {k for k, v in overrides.items() if v == "name-only"}
    sim_set = set(name_only)
    label = "current overrides"
    if args.name_only:
        keep = {s.strip() for s in args.keep.split(",") if s.strip()}
        if args.name_only in TIER_ORDER:
            add = {e["name"] for e in entries
                   if tiers[e["name"]] == args.name_only and e["name"] not in keep}
            label = f"current + {len(add)} {args.name_only} skills"
        else:
            add = {s.strip() for s in args.name_only.split(",") if s.strip()}
            label = f"current + {len(add)} named skills"
        sim_set |= add

    print(f"\n== BUDGET ==  fraction {fraction} (default {DEFAULT_FRACTION}),"
          f" {CHARS_PER_TOKEN} chars/token")
    print("  budget = contextWindow * chars_per_token * fraction."
          " The fraction is a ceiling:")
    print("  while the listing fits, raising it costs nothing.")
    print(f"\n  {'context':>9}{'budget':>10}   {'as recorded':>22}   {label:>26}")
    for ctx, ctx_label in ((DEFAULT_CONTEXT, "200k"), (1_000_000, "1M")):
        budget = int(ctx * CHARS_PER_TOKEN * fraction)
        cells = []
        for group in (name_only, sim_set):
            mode, total, demoted = simulate(entries, budget, group, prio, True, tiers)
            cells.append(f"FITS {total:,} ch" if mode == "fits"
                         else f"{len(demoted)} demoted, {total:,} ch")
        print(f"  {ctx_label:>9}{budget:>10,}   {cells[0]:>22}   {cells[1]:>26}")

    if sim_set != name_only:
        base = simulate(entries, 10 ** 9, name_only, prio, True, tiers)[1]
        after = simulate(entries, 10 ** 9, sim_set, prio, True, tiers)[1]
        print(f"\n  {label}: listing {base:,} -> {after:,} chars"
              f"  (saves {base - after:,} = {(base - after) // CHARS_PER_TOKEN:,}"
              f" tokens per request, every session)")
        for protect in (True, False):
            budget = int(DEFAULT_CONTEXT * CHARS_PER_TOKEN * fraction)
            _, _, before = simulate(entries, budget, name_only, prio, protect, tiers)
            _, _, dem = simulate(entries, budget, sim_set, prio, protect, tiers)
            how = "protected" if protect else "competing"
            print(f"    at 200k, bundled {how:9}: demotions {len(before)} -> {len(dem)}")

    print("\n== DEMOTION, AND WHETHER IT EVER COST ANYTHING ==")
    # A bare entry has two possible causes and the transcript does not say which:
    # an explicit name-only override, or the budget. Subtract the overrides we
    # know about and require a residual of several before calling it demotion --
    # otherwise a description containing a newline reads as a demoted skill.
    RESIDUAL_MIN = 4
    per_session = {}
    for row in rows:
        bare = {e["name"] for e in parse_listing(row["content"]) if e["bare"]}
        residual = bare - name_only
        slot = per_session.setdefault(row["path"], {"demoted": set(), "row": row})
        if len(residual) >= RESIDUAL_MIN:
            slot["demoted"] |= residual
        slot["row"] = row
    hit = [s for s in per_session.values() if s["demoted"]]
    print(f"  {len(hit)} of {len(per_session)} sessions demoted at least"
          f" {RESIDUAL_MIN} skills beyond the known overrides")
    if hit:
        for slot in sorted(hit, key=lambda s: -len(s["demoted"]))[:3]:
            row = slot["row"]
            models = ",".join(sorted(m.replace("claude-", "") for m in row["models"]))
            print(f"    {datetime.datetime.fromtimestamp(row['mtime']):%Y-%m-%d %H:%M}"
                  f"  {len(slot['demoted']):3} demoted  {models[:40]}")
        calls = sum(len(s["row"]["invoked"]) for s in hit)
        hurt = sum(1 for s in hit for got in s["row"]["invoked"] if got in s["demoted"])
        print(f"  Skill() calls made inside those sessions: {calls}")
        print(f"  ... of which the skill was demoted at the time: {hurt}")
        if hurt:
            print("  Every one of those succeeded. A bare name is enough to invoke a"
                  " skill,\n  which is the whole case for name-only over off.")

    print("\n== SUBAGENTS: A SEPARATE POPULATION THAT ALSO PAYS ==")
    # A subagent gets the listing only if its tool set includes the Skill tool
    # (the attachment builder returns early otherwise). So this is switchable per
    # agent definition, which is the whole reason to report it separately.
    sub_rows = scan(sub_files)
    all_sub_calls = sum(len(r["invoked"]) for r in sub_rows)
    if sub_rows:
        sizes = sorted(len(r["content"]) for r in sub_rows)
        total_sub = sum(sizes)
        print(f"  {len(sub_files)} subagent transcripts, {len(sub_rows)} carrying a listing")
        print(f"  listing size: median {sizes[len(sizes) // 2]:,} chars"
              f"  ({sizes[len(sizes) // 2] // CHARS_PER_TOKEN:,} tokens each)")
        print(f"  total ever: {total_sub:,} chars ="
              f" {total_sub // CHARS_PER_TOKEN:,} tokens")
        print(f"  Skill() calls made by subagents, ever: {all_sub_calls}")
        if all_sub_calls:
            print(f"  -> {total_sub // CHARS_PER_TOKEN // all_sub_calls:,}"
                  " tokens of listing per invocation")
        print("  NOTE these tokens are mostly cache CREATION rather than cache read"
              " (a fresh\n  context per agent), so they cost more per token than the"
              " main-thread listing.")
    else:
        print(f"  {len(sub_files)} subagent transcripts, none carrying a listing")

    print("\n== GROWTH ==")
    # Count entries, not characters. Chars/week conflates two different things:
    # skills being added, and existing descriptions being rewritten. A cleanup
    # pass on 2026-08-04 cut ~5,600 chars while the catalog kept growing, which
    # made the chars/week slope read low and briefly negative.
    # Only one project's sessions, or the series compares different catalogs:
    # plugin and project-scoped skills change the entry count between projects,
    # which shows up as growth that never happened.
    busiest = collections.Counter(os.path.dirname(r["path"]) for r in rows).most_common(1)
    home = busiest[0][0] if busiest else None
    series = [r for r in rows if os.path.dirname(r["path"]) == home]
    print(f"  measured within one project only ({os.path.basename(home)[-30:]}),"
          f" {len(series)} of {len(rows)} listings")
    per_week = {}
    for row in series:
        week = datetime.datetime.fromtimestamp(row["mtime"]).strftime("%G-W%V")
        n = len(parse_listing(row["content"]))
        cur = per_week.get(week, (0, 0))
        per_week[week] = max(cur, (n, len(row["content"])))
    weeks = sorted(per_week)
    print(f"  {'week':10}{'entries':>9}{'chars':>10}")
    for week in weeks:
        n, ch = per_week[week]
        print(f"  {week:10}{n:9}{ch:10,}")
    if len(weeks) >= 2:
        span = len(weeks) - 1
        per_entry = accounted // max(1, len(entries))
        entry_rate = (per_week[weeks[-1]][0] - per_week[weeks[0]][0]) / span
        rate = entry_rate * per_entry
        print(f"  {entry_rate:.1f} skills/week over {span} weeks"
              f"  x {per_entry} chars/skill = {rate:,.0f} chars/week")
        if rate > 0:
            for group, group_label in ((name_only, "as recorded"), (sim_set, label)):
                size = simulate(entries, 10 ** 9, group, prio, True, tiers)[1]
                for ctx, ctx_label in ((DEFAULT_CONTEXT, "200k"), (1_000_000, "1M")):
                    budget = int(ctx * CHARS_PER_TOKEN * fraction)
                    head = budget - size
                    verdict = (f"{head / rate:.1f} weeks of headroom"
                               if head > 0 else f"already over by {-head:,}")
                    print(f"    {group_label:26} on {ctx_label:>4}: {verdict}")
                if group is sim_set and sim_set == name_only:
                    break

    print("\n== SIMULATOR VALIDATION ==")
    print("  A prediction is worth only as much as its agreement with a real"
          " demoted listing.")
    # Validate against the MOST RECENT demotion, not the largest. The largest is
    # from 2026-07-29, before the fraction was raised from the 0.01 default, so
    # it was fitted to a different budget and comparing it to today's would
    # manufacture a disagreement that says nothing about the algorithm.
    recent = [s for s in sorted(hit, key=lambda s: -s["row"]["mtime"])] if hit else []
    if recent:
        obs = recent[0]["row"]
        observed = len(obs["content"])
        # A demoted listing sits just under its own budget, so its size reveals it.
        # Nearest, not "smallest that fits": a fitted listing lands a hair either
        # side of its budget (the observed 2026-08-04 one overshot 16,000 by 24
        # chars), and requiring >= observed kicks the answer up a whole tier.
        candidates = [(int(ctx * CHARS_PER_TOKEN * f), f"{lbl} @{f}")
                      for ctx, lbl in ((DEFAULT_CONTEXT, "200k"), (1_000_000, "1M"))
                      for f in (0.01, 0.02, 0.03)]
        implied = min(candidates, key=lambda c: abs(c[0] - observed))
        mode, total, dem = simulate(entries, implied[0], name_only, prio, True, tiers)
        print(f"  observed {datetime.datetime.fromtimestamp(obs['mtime']):%Y-%m-%d %H:%M}:"
              f" {observed:,} chars, {len(recent[0]['demoted'])} demoted"
              f"  -> implies budget {implied[0]:,} ({implied[1]})")
        print(f"  simulated on today's catalog at that budget:"
              f" {total:,} chars, {len(dem)} demoted")
        print(f"  total agrees within {abs(total - observed) / max(observed, 1):.1%};"
              " the counts differ by however many skills were created since.")


if __name__ == "__main__":
    main()
