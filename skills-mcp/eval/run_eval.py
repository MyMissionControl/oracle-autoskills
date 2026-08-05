#!/usr/bin/env python3
"""run_eval.py — score the ranker against pairs.json, broken down by language.

Run this before AND after any change to tokenization, field weights or BM25
parameters. A change that looks like a clean win on three cherry-picked queries
has already cost this project once: trimming one skill's body improved the three
prompts it was tested on and dropped overall recall@3 from 100% to 93%.

The breakdown by language is not decoration. This machine's user writes Thai,
the tokenizer is latin-only by design, and an aggregate number hides that a
whole class of queries scores zero. Read the `mixed thai+latin` row first — it
is the one that describes real traffic here.

`fires` and `precision when fired` model the retrieve-hook, not the tool: the
hook only injects hits at or above SKILLS_HOOK_MIN_SCORE, so a ranking win below
that line changes nothing in practice.

Usage:
  python3 run_eval.py [--pairs pairs.json] [--min-score 15.0] [--verbose]
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import server  # noqa: E402

THAI = re.compile(r"[฀-๿]")


def group_of(query: str) -> str:
    has_latin = bool(server._tokens(query))
    if not has_latin:
        return "thai-only (no latin)"
    return "mixed thai+latin" if THAI.search(query) else "latin-only"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=os.path.join(HERE, "pairs.json"))
    ap.add_argument("--min-score", type=float,
                    default=float(os.environ.get("SKILLS_HOOK_MIN_SCORE") or 15.0))
    ap.add_argument("--verbose", action="store_true", help="print every miss")
    args = ap.parse_args()

    with open(args.pairs, encoding="utf-8") as fh:
        pairs = json.load(fh)
    entries, _excluded = server.build_index()

    groups, misses = {}, []
    for pair in pairs:
        query, expect = pair["query"], pair["expect"]
        searchable = server._has_searchable_terms(query)
        hits = server.retrieve(entries, query, k=5) if searchable else []
        ranked = [h["name"] for h in hits]
        top = hits[0].get("score") if hits else None
        # None means the name-exact layer matched, which outranks any score.
        fired = bool(hits) and (top is None or top >= args.min_score)

        row = groups.setdefault(group_of(query), dict(n=0, a1=0, r3=0, r5=0, fired=0, fired_ok=0))
        row["n"] += 1
        row["a1"] += ranked[:1] == [expect]
        row["r3"] += expect in ranked[:3]
        row["r5"] += expect in ranked[:5]
        if fired:
            row["fired"] += 1
            row["fired_ok"] += ranked[:1] == [expect]
        if expect not in ranked[:3]:
            misses.append((query, expect, ranked[:3]))

    print(f"index: {len(entries)} skills   pairs: {len(pairs)}   "
          f"min-score: {args.min_score}")
    print(f"{'group':24}{'n':>4}{'acc@1':>8}{'rec@3':>8}{'rec@5':>8}"
          f"{'fires':>8}{'prec|fired':>12}")
    total = dict(n=0, a1=0, r3=0, r5=0, fired=0, fired_ok=0)
    for name in sorted(groups):
        row = groups[name]
        for key in total:
            total[key] += row[key]
        prec = f"{100 * row['fired_ok'] / row['fired']:.0f}%" if row["fired"] else "-"
        print(f"{name:24}{row['n']:>4}{100 * row['a1'] / row['n']:7.0f}%"
              f"{100 * row['r3'] / row['n']:7.0f}%{100 * row['r5'] / row['n']:7.0f}%"
              f"{100 * row['fired'] / row['n']:7.0f}%{prec:>12}")
    prec = f"{100 * total['fired_ok'] / total['fired']:.0f}%" if total["fired"] else "-"
    print(f"{'ALL':24}{total['n']:>4}{100 * total['a1'] / total['n']:7.0f}%"
          f"{100 * total['r3'] / total['n']:7.0f}%{100 * total['r5'] / total['n']:7.0f}%"
          f"{100 * total['fired'] / total['n']:7.0f}%{prec:>12}")

    if args.verbose:
        print(f"\n{len(misses)} miss(es) — expected skill absent from top 3:")
        for query, expect, ranked in misses:
            print(f"  want {expect}")
            print(f"   got {ranked}")
            print(f"     q {query[:100]!r}")


if __name__ == "__main__":
    main()
