#!/usr/bin/env python3
"""Tests for listing_report.py, aimed squarely at the mistakes it was written
after making. Both of the parsing bugs below produced plausible, wrong numbers
that survived several rounds of analysis, so they get assertions rather than
comments.

  python3 eval/test_listing_report.py
"""
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import listing_report as lr  # noqa: E402

checks = 0


def ok(cond, label):
    global checks
    checks += 1
    if not cond:
        raise AssertionError(label)


# -- parse_listing --------------------------------------------------------
# A description may contain a newline. Treating its continuation as an entry
# both invents a skill and drops the continuation's characters from the total;
# that discrepancy is what made two hand computations of the same listing
# disagree by 3,390 chars.
content = "\n".join([
    "- alpha: does a thing",
    "- beta: line one",
    "  line two of the same description",
    "- gamma: does another thing",
])
ents = lr.parse_listing(content)
ok(len(ents) == 3, "continuation line must not count as an entry")
ok([e["name"] for e in ents] == ["alpha", "beta", "gamma"], "names in order")
accounted = sum(e["entry_len"] for e in ents) + len(ents) - 1
ok(accounted == len(content), f"every char accounted: {accounted} != {len(content)}")

bare = lr.parse_listing("- alpha\n- beta: has a description")
ok(bare[0]["bare"] and not bare[1]["bare"], "bare entries detected by missing ': '")

# A plugin-qualified name carries a colon of its own and must still parse.
q = lr.parse_listing("- superpowers:writing-plans: use when planning")
ok(len(q) == 1 and q[0]["name"] == "superpowers", "qualified names parse as one entry")

# -- simulate -------------------------------------------------------------
entries = [{"name": "keep", "entry_len": 200, "bare": False},
           {"name": "drop", "entry_len": 200, "bare": False},
           {"name": "tiny", "entry_len": 20, "bare": False}]
tiers = {"keep": "auto", "drop": "auto", "tiny": "auto"}
prio = {"keep": 10.0, "drop": 0.0, "tiny": 0.0}.get

mode, total, demoted = lr.simulate(entries, 10_000, set(), prio, True, tiers)
ok(mode == "fits" and not demoted, "under budget nothing is demoted")
ok(total == 200 + 200 + 20 + 2, "fits-mode total is the sum plus newlines")

mode, total, demoted = lr.simulate(entries, 240, set(), prio, True, tiers)
ok(mode == "priority", "over budget switches to priority mode")
ok("keep" in [e["name"] for e in entries] and "keep" not in demoted,
   "highest priority keeps its description")
ok("drop" in demoted, "zero-priority long entry is demoted")
ok("tiny" not in demoted,
   "greedy fit continues past a miss: a small entry still fits after a big one is skipped")
ok(total <= 240, f"priority-mode total stays within budget: {total}")

# name-only is charged as a bare name AND exempted from the competition, which
# is the entire mechanism by which it hands budget to other skills.
_, total_no, demoted_no = lr.simulate(entries, 240, {"drop"}, prio, True, tiers)
ok("drop" not in demoted_no, "a name-only skill is not reported as demoted")
ok(total_no < total + 200, "name-only removes its description from the total")

_, free_all, _ = lr.simulate(entries, 10 ** 9, {"drop"}, prio, True, tiers)
ok(free_all == 200 + len("drop") + 2 + 20 + 2,
   f"name-only is charged as '- name': {free_all}")

# -- _when ----------------------------------------------------------------
# The record's own timestamp, not the file's mtime: a long session's file is
# touched every turn, so mtime reports a two-day-old listing as current.
here = os.path.abspath(__file__)
parsed = lr._when({"timestamp": "2026-08-05T15:55:00.000Z"}, here)
ok(datetime.datetime.fromtimestamp(parsed, datetime.timezone.utc)
   .strftime("%Y-%m-%dT%H:%M") == "2026-08-05T15:55",
   "iso timestamp is parsed as UTC, not as local time")
ok(lr._when({}, here) == os.path.getmtime(here), "falls back to mtime")
ok(lr._when({"timestamp": "not a date"}, here) == os.path.getmtime(here),
   "an unparseable timestamp falls back rather than raising")

# -- tier_of --------------------------------------------------------------
ok(lr.tier_of("definitely-not-a-real-skill-xyz", "/nonexistent") == "builtin/plugin",
   "a skill with no SKILL.md on disk is builtin or plugin")

print(f"PASS {checks} assertions")
