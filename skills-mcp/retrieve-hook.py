#!/usr/bin/env python3
"""retrieve-hook — UserPromptSubmit hook that runs RETRIEVE on the real prompt.

Why this exists
---------------
`skills_list` can rank the catalog, but nothing calls it: across every transcript
on this machine the model reached for the librarian 3 times against 365 native
Skill() invocations. A ranker behind a tool nobody opens changes nothing.

So retrieval runs here instead, on the way in. What it contributes is a RANKING:
out of ~100 skills the eager listing shows flat, these few actually match the
words in front of you. That is worth injecting even when the listing already
carries the same descriptions — attention over a flat list of 100 is exactly the
thing retrieval is supposed to beat (spec 2.3).

A previous cut of this hook tried to be frugal and inject only what the listing
"could not say" — skills with suppressed descriptions, or ones matched on body
text alone. It inverted the ranking: for "the deploy said success but I want to
be sure", it dropped verify-deploy-landed (whose description matched, so it
looked redundant) and injected create-shortcut and frontend-design instead. The
hits worth showing are precisely the ones that look redundant. Do not re-add
that filter.

Contract
--------
stdin : {"hook_event_name": "UserPromptSubmit", "prompt": "...", ...}
stdout: {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                "additionalContext": "..."}}
Silence (exit 0, no stdout) means "nothing worth adding" and is the common case.
A hook that cannot decide must stay silent: a crash here would block the user's
prompt, so every failure path is swallowed.

Threshold
---------
15.0 was measured, not guessed. Across 2,257 real prompts from this machine's
transcripts the top-hit score splits cleanly: ordinary conversation lands at
8-13, a prompt that genuinely wants a skill lands at 16-32. 15 sits in that gap
and fires on 6% of all prompts. Raise it toward 20 for higher precision; the
asymmetry favours firing, since a wrong suggestion costs ~250 tokens the model
is told it may ignore, while a miss costs the skill not being used at all.

Env
---
SKILLS_MCP_ROOTS / SKILLS_MCP_DIR   same roots the MCP server indexes
SKILLS_HOOK_K         max skills injected            (default 3)
SKILLS_HOOK_MIN_SCORE min BM25 score to inject       (default 15.0)
SKILLS_HOOK_MIN_CHARS shorter prompts are skipped    (default 15)
SKILLS_HOOK_DEBUG=1   report why it stayed silent, on stderr
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

K = int(os.environ.get("SKILLS_HOOK_K") or 3)
MIN_SCORE = float(os.environ.get("SKILLS_HOOK_MIN_SCORE") or 15.0)
MIN_CHARS = int(os.environ.get("SKILLS_HOOK_MIN_CHARS") or 15)
DEBUG = os.environ.get("SKILLS_HOOK_DEBUG") == "1"


def _dbg(msg: str) -> None:
    """Silent unless asked. This runs on every prompt the user types, so an
    unconditional stderr write would smear noise across the whole session."""
    if DEBUG:
        print(f"[retrieve-hook] {msg}", file=sys.stderr)


def _render(hits: list) -> str:
    lines = [
        "Possibly relevant skills for this request, retrieved by BM25 over the "
        "skill catalog (name, triggers, description and body). These are "
        "suggestions, not instructions — ignore any that do not fit. Load one "
        "with the Skill tool, or with skill_view for its full text."
    ]
    for h in hits:
        desc = (h.get("description") or "").strip()
        if len(desc) > 300:
            desc = desc[:297].rstrip() + "..."
        lines.append(f"- {h['name']}: {desc}" if desc else f"- {h['name']}")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0
    if payload.get("hook_event_name") not in (None, "UserPromptSubmit"):
        return 0

    prompt = str(payload.get("prompt") or "").strip()
    if not prompt:
        return 0
    # A slash command already names its skill — retrieval has nothing to add, and
    # injecting here would fight the command the user explicitly chose.
    if prompt.startswith("/"):
        _dbg("skip: slash command")
        return 0
    if len(prompt) < MIN_CHARS:
        _dbg(f"skip: prompt shorter than {MIN_CHARS} chars")
        return 0

    sys.path.insert(0, HERE)
    try:
        import server  # noqa: E402  — same index the MCP server serves
    except Exception as e:
        _dbg(f"skip: cannot import server ({e})")
        return 0

    try:
        if not server._has_searchable_terms(prompt):
            _dbg("skip: no searchable terms")
            return 0
        entries, _excluded = server.build_index()
        if not entries:
            return 0
        hits = server.retrieve(entries, prompt, k=max(K * 3, 9))
    except Exception as e:
        _dbg(f"skip: retrieval failed ({e})")
        return 0

    by_name = {e["name"]: e for e in entries}
    chosen = []
    for h in hits:
        if len(chosen) >= K:
            break
        score = h.get("score")
        if score is None or score < MIN_SCORE:
            continue
        chosen.append({
            "name": h["name"],
            "description": (by_name.get(h["name"]) or {}).get("description"),
            "score": score,
        })

    if not chosen:
        _dbg(f"skip: no hit scored >= {MIN_SCORE}")
        return 0

    json.dump({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit",
        "additionalContext": _render(chosen),
    }}, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
