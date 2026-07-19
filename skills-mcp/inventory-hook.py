#!/usr/bin/env python3
"""Channel C — PreToolUse hook that deterministically injects the agent's tool
inventory into skills_list calls, so Feature 4 (conditional visibility) never
depends on the model remembering to pass agent_tools.

Register in settings.json:
  "PreToolUse": [{ "matcher": "mcp__skills__skills_list",
                   "hooks": [{ "type": "command",
                               "command": "python3 ~/.claude/skills-mcp/inventory-hook.py" }]}]

Runs inside the harness (gets session_id/transcript_path). Reads a PreToolUse
payload on stdin and prints a hookSpecificOutput with updatedInput. If anything
is uncertain it passes the call through unchanged — degrades to the server's own
Channel A/B behavior, never below it.
"""

import json
import os
import sys

# Mirror server.py::BUILTIN_TOOLS — always present in Claude Code.
BUILTIN_TOOLS = [
    "Bash", "Read", "Edit", "Write", "Glob", "Grep", "LS", "List",
    "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite", "NotebookEdit",
    "Skill", "MultiEdit", "ExitPlanMode",
]


def registered_mcp_tools():
    """Server names + a best-effort tool-prefix from ~/.claude.json. We can't
    enumerate individual MCP tools from config, so we expose the server names;
    skills should gate on requires.mcp (server-level, checked server-side) for
    MCP deps. Returned here so requires.tools referencing a server still matches."""
    names = []
    try:
        with open(os.path.expanduser("~/.claude.json"), "r", encoding="utf-8") as f:
            top = json.load(f)
        for k in (top.get("mcpServers") or {}):
            names.append(k)
        for _p, cfg in (top.get("projects") or {}).items():
            if isinstance(cfg, dict):
                for k in (cfg.get("mcpServers") or {}):
                    names.append(k)
    except Exception:
        pass
    return names


def deferred_tools_from_transcript(path):
    """Best-effort: recover deferred/available tool names recorded in the session
    transcript. Undocumented format — failure returns [] (graceful degradation)."""
    if not path or not os.path.isfile(path):
        return []
    found = set()
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            for line in f:
                # Deferred-tool system reminders list names like mcp__x__y and
                # built-in tool names; capture obvious tool tokens conservatively.
                if "deferred tools" in line or "mcp__" in line:
                    for tok in line.replace('"', " ").replace(",", " ").split():
                        if tok.startswith("mcp__"):
                            found.add(tok)
    except Exception:
        return []
    return sorted(found)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return  # no output -> call proceeds unchanged

    tool_name = payload.get("tool_name", "")
    if not tool_name.endswith("skills_list"):
        return  # not our tool

    tool_input = dict(payload.get("tool_input") or {})
    # Do not clobber an inventory the model already supplied.
    if tool_input.get("agent_tools"):
        return

    inventory = list(BUILTIN_TOOLS)
    inventory += registered_mcp_tools()
    inventory += deferred_tools_from_transcript(payload.get("transcript_path"))
    # de-dup, stable
    seen, uniq = set(), []
    for t in inventory:
        if t not in seen:
            seen.add(t)
            uniq.append(t)
    tool_input["agent_tools"] = uniq

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecisionReason": "skills-mcp: injected agent tool inventory",
            "updatedInput": tool_input,
        }
    }))


if __name__ == "__main__":
    main()
