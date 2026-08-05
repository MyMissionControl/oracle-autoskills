---
name: graphify-codegraph-token-tool
description: 'Set up graphify to cut agent tokens on a large/read-only codebase: install graphifyy robustly, build a code-graph LLM-free without dirtying the repo, query it instead of reading whole files.'
installer: auto-skill
created_at: 2026-07-17T22:35:32+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-opus-graphify-audit
category: token-optimization
content_hash: 19c245b4cc1a523e3568669900ea2a70f9b6881d173ffb7f732e292451ba60e1
---
# Set up graphify as a token-saving code-graph query tool

Use when you want to cut agent tokens navigating a LARGE, stable/read-only codebase by querying a code-graph instead of reading whole files — or when asked to "set up graphify". Not worth it for small, fast-changing repos (rg is cheaper and the graph goes stale on every edit).

## Steps

1. **Install robustly.** graphify is a uvx tool package `graphifyy`, NOT a PATH binary — `which graphify` reports "missing" even when it is cached in `~/.cache/uv`. Install to a STABLE bin dir, overriding the tool dir because some sandboxes (e.g. a VSCode snap) point `XDG_DATA_HOME` at an ephemeral revisioned path:
   ```bash
   UV_TOOL_DIR="$HOME/.local/share/uv/tools" UV_TOOL_BIN_DIR="$HOME/.local/bin" uv tool install graphifyy --force
   which graphify graphify-mcp   # confirm on PATH
   ```

2. **Build the graph LLM-free, without dirtying the repo.** `update --no-cluster` is pure AST (no API key, auto-skips node_modules/.git). It writes `<repo>/graphify-out/graph.json` INSIDE the repo:
   ```bash
   graphify update <repo> --no-cluster      # ~40-50s for a 200-300K-LOC repo
   ```

3. **Relocate the graph out of the repo** (keeps the working tree pristine; matches the `~/.oracle/graphify/<name>/` convention some tools expect):
   ```bash
   mkdir -p ~/.oracle/graphify/<name>
   mv <repo>/graphify-out/graph.json ~/.oracle/graphify/<name>/graph.json
   rm -rf <repo>/graphify-out
   git -C <repo> status --porcelain | grep graphify   # expect no output = pristine
   ```

4. **Query instead of reading whole files** (compact, file:line-anchored, ~budget-capped):
   ```bash
   graphify query "<question>" --graph ~/.oracle/graphify/<name>/graph.json --budget 1200   # BFS
   graphify path "SymbolA" "SymbolB" --graph ...        # shortest path between two nodes
   graphify affected "X" --graph ...                    # reverse impact; X = EXACT node label from a prior query
   ```

## Notes / gotchas
- `update`/`--no-cluster` never touch git hooks or `.gitattributes`; only the explicit `install`/merge-driver commands do — don't run those on a repo you want kept clean.
- `affected`/`path` need EXACT node labels (run `query` first to see them); `query` is the primary tool.
- Rebuild after big changes with the same step 2+3. On small/active repos, prefer `rg` — don't build a graph you must constantly refresh.
- `graphify-mcp` serves ONE graph per server. Registering it puts always-on tool schemas in every session's context — for occasional use, prefer the CLI on-demand; only register MCP if graph queries become frequent.
