# skills-mcp — a librarian for the skill catalog

A zero-dependency Python stdio MCP server over every `SKILL.md` in
`~/.claude/skills`. Three tools: list the catalog, read a skill, patch a skill.
The index lives in process memory and costs nothing in context; it is read only
when a tool is called.

**The BM25 ranker and the `UserPromptSubmit` hook were REMOVED on 2026-08-07.**
`skills_list` no longer takes `query`, `k` or `pinned`; it returns the catalog
alphabetically, filtered by `category` if you pass one — the shape Hermes ships.
Why, in one line: Claude Code already puts every skill's name and description in
the system prompt at t0 as stage 1 of the agentskills.io progressive-disclosure
spec, so a ranker can only run after the model has decided, is billed uncached,
and must throw away candidates the model could already see. Measured here: 358
`Skill()` invocations against 3 `skills_list` calls, 42% acc@1 against a
mechanism that structurally cannot miss, and 2 of 80 delivered hook suggestions
adopted. Full reasoning: `soulbrew/mdFile/skill-discovery-*.md`.

## What this is NOT

It is not a replacement for Claude Code's eager skill listing, and an earlier
version of this README claimed it was. That claim was measured on 2026-08-05 and
is false.

The eager listing is not a search — it is the absence of one. Every skill's
`name`+`description` sits in the system prompt, and the **model** does the
matching, with the conversation, the working directory and the user's language all
available to it. Retrieval has to pick 3 of ~100 by counting word overlap, before
the model has thought about anything, seeing only latin tokens. A filter competing
against no-filter can only lose recall. The one thing it can win is cost.

The numbers, on an eval derived from real transcript decisions (`eval/`):

| | acc@1 | recall@3 |
|---|---|---|
| BM25 over prompt text | 34% | 63% |
| `cwd` alone, reading none of the prompt | **57%** | 61% |

Knowing which folder the user is in beats reading every word they typed. The
model has both signals; BM25 has only the English words.

Six attempts to close that gap all measured worse than plain BM25: agent-rewritten
English queries (13%), truncating long prompts (5-31%), dense bge-m3 embeddings
(21%), RRF fusion of BM25+dense (29%), Thai character n-grams (**1.6%** — a Thai
sentence yields ~10x more n-grams than an English sentence yields words, which
swamps the real signal), and mining `triggers:` from usage history. Do not
re-propose these without new evidence; see the notes in `server.py`. The ranker
they were tuning no longer exists.

## What it is for

1. **Skills Claude Code cannot see.** A skill directory outside `~/.claude/skills`
   has no listing entry, no `Skill()` availability and no `/name` — but
   `skills_list` finds it and `skill_view` returns its body for the model to
   follow directly. This is the only capability the listing cannot have.
   Caution: the previous two-pile design relied on exactly this and 8 of the 9
   relocated skills went untouched for 17 days. Hidden turned out to mean dead.
2. **Skills whose description is suppressed.** `skillOverrides: name-only` gets
   the description tokens back while keeping the skill invocable; retrieval is
   then the only route to what it does.
3. **Body-text matches** the description does not mention (worth ~+2 acc@1).
4. **Insurance for listing-budget overflow.** Over budget, the CLI silently
   rewrites low-priority entries to bare names. On that day retrieval is the only
   thing standing between a demoted skill and oblivion. It has to exist before it
   is needed, which is why it looks near-idle now.

## Tools

- `skills_list(query?, k?, pinned?, category?, agent_tools?, agent_toolsets?, all?)`
  — with `query`, BM25-ranked hits carrying `score` and `matched_by`; without it,
  the catalog (compact, names only, once past `FULL_DUMP_MAX`). Hides skills whose
  required tools/MCP servers are unavailable (mcp checked server-side from
  `~/.claude.json`; tools via `agent_tools`).
- `skill_view(name, file_path?)` — a skill's body, or a linked reference file on
  demand; includes a readiness report (missing env/commands/files/mcp).
- `skill_patch(name, old_string, new_string, edited_by?)` — repair a skill's body;
  re-stamps `content_hash` + `edited_by`/`edited_at` provenance.

Retrieval layers, cheapest first, stopping at `k`: `pinned` → `name-exact` →
`bm25`. The first two return **no score** on purpose, so that no threshold can
filter them out — a caller treating `score is None` as "below threshold" throws
away the highest-confidence signal in the system.

## Files

| file | role |
|---|---|
| `server.py` | the MCP server: index + the 3 tools. No ranking since 2026-08-07 |
| `inventory-hook.py` | PreToolUse hook: injects agent tool inventory into `skills_list` |
| `janitor.py` | reports cold auto-skills; `--apply` writes `skillOverrides`, moves nothing |
| `eval/build_pairs.py` | derives an eval set from transcript turns where the MODEL invoked a skill |
| `eval/run_eval.py` | **RETIRED** — scored the removed ranker. Kept as a worked example of building an eval from logged model decisions |
| `test_server.py`, `test_retrieve_hook.py` | 84 + 32 assertions |

## Setup

```bash
# 1. register the server (user scope = all projects)
claude mcp add skills -s user \
  -e SKILLS_MCP_ROOTS=$HOME/.claude/skills \
  -- python3 $HOME/.claude/skills-mcp/server.py

# 2. PreToolUse hook, matcher mcp__skills__skills_list
#    command: python3 $HOME/.claude/skills-mcp/inventory-hook.py

# 3. (optional) weekly janitor, report-only
#    0 17 * * 0  python3 $HOME/.claude/skills-mcp/janitor.py
```

Reload the Claude Code window after registering, and after any change to
`skillOverrides` — the eager listing is built at startup.

`SKILLS_MCP_ROOTS` is a comma-separated list; earlier roots shadow later ones on a
name collision, and every exclusion is reported with a reason. `SKILLS_INDEX_NO_BODY`
is gone: it existed to keep catch-all bodies out of the BM25 index, and bodies are
no longer indexed at all.

## Deployment note

This is the source of truth; the runtime copy lives at `~/.claude/skills-mcp/`.
They are plain copies, not symlinks — `cp` after editing, and diff against
`git show HEAD:skills-mcp/<file>` before overwriting in case the live copy drifted.
