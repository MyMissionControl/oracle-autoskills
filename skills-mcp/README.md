# skills-mcp — lazy skill librarian

A zero-dependency Python stdio MCP server that serves the skill catalog **on
demand**, so skills live in tool-output (O(1) always-on context) instead of
Claude Code's eager O(N) system-prompt injection. Ports Hermes'
`skills_list`/`skill_view` model to Claude Code via MCP.

## Why

Claude Code injects every skill's `name`+`description` into every session's
system prompt — cost grows linearly with skill count, paid per session. This
server moves the catalog into a tool response: the model calls `skills_list` to
discover, `skill_view` to load. Skills kept in `~/.claude/skills` stay eager
(native `Skill()` invocation); cold ones are moved to `~/.claude/skills-lib`
(served only here) to keep the eager listing bounded.

## Tools

- `skills_list(category?, agent_tools?, agent_toolsets?, all?)` — the catalog;
  hides skills whose required tools/MCP servers are unavailable (mcp checked
  server-side from `~/.claude.json`; tools via `agent_tools`).
- `skill_view(name, file_path?)` — a skill's body, or a linked reference file on
  demand; includes a readiness report (missing env/commands/files/mcp).
- `skill_patch(name, old_string, new_string, edited_by?)` — repair a skill's
  body; re-stamps `content_hash` + `edited_by`/`edited_at` provenance.

## Files

| file | role |
|---|---|
| `server.py` | the MCP server (stdlib + PyYAML) |
| `inventory-hook.py` | PreToolUse hook: injects agent tool inventory into `skills_list` (Channel C) |
| `janitor.py` | sweeps cold auto-skills (0 native invocations, >7d) into skills-lib |
| `test_server.py` | end-to-end test (`python3 test_server.py`) |

## Setup

```bash
# 1. register the server (user scope = all projects)
claude mcp add skills -s user \
  -e SKILLS_MCP_DIR=$HOME/.claude/skills-lib \
  -- python3 $HOME/.claude/skills-mcp/server.py

# 2. hook (settings.json PreToolUse), matcher: mcp__skills__skills_list
#    command: python3 $HOME/.claude/skills-mcp/inventory-hook.py

# 3. preamble in ~/.claude/CLAUDE.md nudging skills_list / skill_view / skill_patch

# 4. (optional) weekly janitor
#    0 11 * * 0  python3 $HOME/.claude/skills-mcp/janitor.py --apply
```

Reload the Claude Code window after registering / after any janitor `--apply`.

`SKILLS_MCP_DIR` selects what the server serves: point it at `~/.claude/skills`
to serve everything (eager stays too), or at `~/.claude/skills-lib` for the
lazy-only tail (recommended, with hot/invoked skills kept eager).

## Deployment note

This is the source of truth; the runtime copy lives at `~/.claude/skills-mcp/`.
