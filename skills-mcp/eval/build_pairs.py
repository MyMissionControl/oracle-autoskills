#!/usr/bin/env python3
"""build_pairs.py — derive a retrieval eval set from what actually happened.

The first eval for this ranker was 16 queries I wrote by hand, and it scored
87% acc@1. On the set this script builds it scores 24%. Hand-written queries
measure how well the ranker matches the query-writer's mental model of the
catalog, which is exactly the thing you cannot be neutral about while tuning it.

Ground truth here is a real decision: a transcript turn where the MODEL chose to
invoke a skill. The prompt that preceded it is the query; the skill it reached
for is the expected answer.

Filters, and why each one is needed:
  - isSidechain            subagent prompts are not user prompts. Forgetting
                           this once made a 5% hook fire-rate read as 60%.
  - user typed the name    "run /rrr" is not retrieval, it is dictation.
  - synthetic prompts      task-notifications, slash commands, compact
                           summaries, hook output: nobody typed them.
  - non-queries            inbox banners, "yes", "continue". A skill call
                           followed them, but they carry no request to match.
  - target not in index    plugin skills (superpowers:*) are exempt from the
                           index by design; scoring them as misses measures
                           nothing.

This is still an imperfect oracle: the model's pick is not proof that no other
skill fitted. Treat the absolute number as soft and the BEFORE/AFTER delta on a
frozen pairs.json as the real signal.

Usage:
  python3 build_pairs.py [--out pairs.json] [--projects ~/.claude/projects]
"""
import argparse
import glob
import json
import os
import re

SYNTHETIC = (
    "<task-notification>", "<command-name>", "<command-message>", "<local-command",
    "<system-reminder>", "[Request interrupted", "Caveat:",
    "This session is being continued", "<user-prompt-submit-hook>", "<ide_selection>",
)
# Skills invoked because of where the session IS, not because of what the last
# message said: retrospectives at wrap-up, wake/handoff at start. The preceding
# prompt is whatever the human happened to type before, so the pair teaches the
# ranker nothing and drags the score down — 21 of 83 pairs here were `rrr`, and
# removing them moved acc@1 from 25% to 34% without a line of code changing.
# They are excluded by default; --keep-lifecycle puts them back.
LIFECYCLE_SKILLS = {"rrr", "awaken", "where-we-are", "incubate", "handoff"}
# Turns that precede a skill call without asking for anything.
NON_QUERY = re.compile(
    r"^(yes|no|ok|okay|continue|go|go ahead|ต่อ|ลุย|ทำเลย|เอาเลย|ครับ|ค่ะ)\W*$",
    re.IGNORECASE,
)
INBOX_BANNER = "unread messages in inbox"
MIN_QUERY_CHARS = 12


def _text(rec: dict) -> str:
    content = rec.get("message", {}).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(c.get("text", "") for c in content
                        if isinstance(c, dict) and c.get("type") == "text")
    return ""


def _is_query(text: str) -> bool:
    if len(text) < MIN_QUERY_CHARS or text.startswith(SYNTHETIC) or text.startswith("/"):
        return False
    if INBOX_BANNER in text or NON_QUERY.match(text.strip()):
        return False
    return True


def harvest(projects: str) -> list[dict]:
    pairs, dictated = [], 0
    for path in glob.glob(os.path.join(projects, "**", "*.jsonl"), recursive=True):
        records = []
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    records.append(json.loads(line))
                except ValueError:
                    continue
        last_prompt = None
        distance = 0
        for rec in records:
            if rec.get("isSidechain"):
                continue
            if rec.get("type") == "user" and not rec.get("isMeta"):
                text = _text(rec).strip()
                if _is_query(text):
                    last_prompt = text
                    distance = 0
            elif rec.get("type") == "assistant":
                distance += 1
                for block in rec.get("message", {}).get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    if block.get("name") != "Skill":
                        continue
                    skill = (block.get("input") or {}).get("skill")
                    if not skill or not last_prompt:
                        continue
                    if skill.lower() in last_prompt.lower():
                        dictated += 1          # the human named it; not a retrieval case
                        continue
                    pairs.append({"query": last_prompt, "expect": skill,
                                  "distance": distance})
    # Keep the CLOSEST occurrence of a (query, skill) pair. `last_prompt` is not
    # cleared once consumed, so one prompt can father every skill call for the
    # rest of a session -- measured p80 = 35 assistant turns, p90 = 97, max 673.
    # (An earlier note here said p80=11/p90=58/max=508; that was measured before
    # the recursive-glob fix, on 23% of the transcripts. Re-run to re-measure --
    # these deciles move with the corpus and go stale silently.)
    # Scoring a ranker on a query issued 97 turns earlier measures transcript
    # bookkeeping, not retrieval: capping distance at 5 moves acc@1 from 34% to
    # 42% and recall@3 from 60% to 68%, without one line of ranker code changing.
    best: dict[tuple[str, str], dict] = {}
    for pair in pairs:
        key = (pair["query"], pair["expect"])
        if key not in best or pair["distance"] < best[key]["distance"]:
            best[key] = pair
    return list(best.values()), dictated


def main() -> None:
    here = os.path.dirname(os.path.abspath(__file__))
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(here, "pairs.json"))
    ap.add_argument("--projects", default=os.path.expanduser("~/.claude/projects"))
    ap.add_argument("--keep-unindexed", action="store_true",
                    help="keep pairs whose target is not in the index (plugin skills)")
    ap.add_argument("--keep-lifecycle", action="store_true",
                    help=f"keep session-lifecycle targets {sorted(LIFECYCLE_SKILLS)}")
    ap.add_argument("--max-distance", type=int, default=0,
                    help="drop pairs whose Skill() call is more than N assistant "
                         "turns after the prompt (0 = keep all). 5 is a defensible "
                         "default: it keeps 77%% of pairs and excludes the tail "
                         "where no ranker could succeed.")
    args = ap.parse_args()

    pairs, dictated = harvest(args.projects)
    if pairs:
        ordered = sorted(p["distance"] for p in pairs)
        deciles = [ordered[min(int(q / 10 * len(ordered)), len(ordered) - 1)]
                   for q in range(1, 10)]
        print("prompt-to-call distance deciles: "
              + " ".join(f"p{q * 10}={d}" for q, d in zip(range(1, 10), deciles))
              + f" max={ordered[-1]}")
    if args.max_distance:
        before = len(pairs)
        pairs = [p for p in pairs if p["distance"] <= args.max_distance]
        print(f"dropped {before - len(pairs)} pair(s) beyond distance "
              f"{args.max_distance}")
    if not args.keep_lifecycle:
        before = len(pairs)
        pairs = [p for p in pairs if p["expect"] not in LIFECYCLE_SKILLS]
        print(f"dropped {before - len(pairs)} session-lifecycle pair(s)")
    if not args.keep_unindexed:
        import sys
        sys.path.insert(0, os.path.dirname(here))
        import server
        indexed = {e["name"] for e in server.build_index()[0]}
        before = len(pairs)
        pairs = [p for p in pairs if p["expect"] in indexed]
        print(f"dropped {before - len(pairs)} pair(s) whose target is not indexed")

    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(pairs, fh, ensure_ascii=False, indent=1)
        fh.write("\n")
    print(f"{len(pairs)} pair(s) -> {args.out}   (skipped {dictated} human-dictated)")


if __name__ == "__main__":
    main()
