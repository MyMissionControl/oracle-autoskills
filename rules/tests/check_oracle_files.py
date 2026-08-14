#!/usr/bin/env python3
"""Drift guard: an oracle's own CLAUDE.md must hold identity ONLY (tier 3).

The fleet drifted the first time because the 5 Principles / Rule 6 / Golden Rules were copy-pasted
into every oracle file — 5 places to edit, and bob still signs an old model. This is the check that
stops the copy-paste from creeping back once tier 1 + 2 are injected by the hook.

Report-only by default so it can be committed BEFORE the oracle files are cleaned up (phase B);
pass --strict to make it a gate once they are.  Run:

    python3 check_oracle_files.py            # report, exit 0
    python3 check_oracle_files.py --strict   # exit 1 if any oracle file still carries tier-1/2 text
    python3 check_oracle_files.py --dir /path/to/owner-dir
"""
import os
import re
import sys

DEFAULT_DIR = os.path.expanduser("~/Desktop/soulbrew/github.com/fufu-2345")

# Headings that belong to tier 1 (universal) or tier 2 (role) — never to an oracle's own file.
BANNED = [
    (r"^##\s+Principles\b", "tier1: Principles"),
    (r"^##\s+The 5 Principles\b", "tier1: The 5 Principles"),
    (r"^##\s+Golden Rules\b", "tier1: Golden Rules"),
    (r"^##\s*.*Rule 6\b", "tier1: Rule 6"),
    (r"^##\s+Inbox Discipline\b", "tier1: Inbox Discipline"),
    (r"^##\s+Request-Reply Protocol\b", "tier1: Request-Reply Protocol"),
    (r"^##\s+Orchestration guardrails\b", "tier2: Orchestration guardrails"),
]


def oracle_files(root):
    if not os.path.isdir(root):
        return []
    out = []
    for name in sorted(os.listdir(root)):
        if not name.endswith("-oracle"):
            continue
        path = os.path.join(root, name, "CLAUDE.md")
        if os.path.isfile(path):
            out.append((name, path))
    return out


def scan(path):
    hits = []
    with open(path, encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            for pattern, label in BANNED:
                if re.search(pattern, line.strip(), re.IGNORECASE):
                    hits.append((i, label, line.strip()))
    return hits


def main(argv):
    strict = "--strict" in argv
    root = DEFAULT_DIR
    if "--dir" in argv:
        root = argv[argv.index("--dir") + 1]

    files = oracle_files(root)
    if not files:
        print("no oracle CLAUDE.md found under %s" % root)
        return 0

    dirty = 0
    for name, path in files:
        hits = scan(path)
        if not hits:
            print("OK   %-16s identity only" % name)
            continue
        dirty += 1
        print("DRIFT %-15s %d shared section(s) still inline:" % (name, len(hits)))
        for line_no, label, text in hits:
            print("        %s:%d  %s  (%s)" % (os.path.basename(path), line_no, label, text[:60]))

    print("\n%d/%d oracle files clean" % (len(files) - dirty, len(files)))
    if dirty and strict:
        print("FAIL (--strict): shared rules must live in rules/, injected by inject_rules.py")
        return 1
    if dirty:
        print("report-only — rerun with --strict once phase B has cleaned these files")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
