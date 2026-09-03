#!/usr/bin/env bash
# Capped launcher for the arra-oracle-v3 MCP server (2026-07-18).
# WHY: alpha's vector path leaks a native LanceDB connection per hybrid search
# (entities.ts queryEntityLinks + LanceDBAdapter.close() never closes db).
# Worker MCPs ballooned to 7-8.5GB and killed the VM 3x today. Legacy repo is
# read-only, so contain it here: hard cgroup cap -> the leaking MCP dies ALONE
# (that session's oracle tools error until reconnect) instead of the whole VM.
# MemorySwapMax matters: with 16G host swap, MemoryMax alone would page out and
# keep growing (thrash) instead of being killed.
# Vector "degraded" is a SELF-SUSTAINING LATCH in alpha (measured 2026-09-03):
# one failed embed sets the process-global flag (threshold 1); getToolCtx() copies
# it into ctx on EVERY tool call; search/handler.ts sees 'degraded' and forces
# effectiveMode='fts', so the vector leg never runs again -- and the flag is only
# cleared by a SUCCESSFUL embed. One 404 (a model name not in config, or a hiccup
# in ollama) therefore kills semantic search for the whole life of the MCP, with
# no self-heal and no error the user can see. That is how it stayed broken for
# weeks. Legacy repo is read-only, so contain it here: raise the threshold so a
# failure degrades ONE query (handler already falls back to FTS per-query) instead
# of latching the process. Boot-time detection is unaffected -- probeEmbedder sets
# degraded directly, bypassing this threshold.
: "${ORACLE_EMBEDDER_FAILURE_THRESHOLD:=1000}"
export ORACLE_EMBEDDER_FAILURE_THRESHOLD

BUN=/home/chillox-intern/.bun/bin/bun
APP=/home/chillox-intern/Desktop/soulbrew/github.com/Soul-Brews-Studio/arra-oracle-v3/src/index.ts

# Per-vault memory isolation (opt-in, OFF by default). The MCP server starts with
# cwd = the oracle's own repo, so the READ tenant is derived from $PWD. Prints
# empty unless that vault is in BOTH "vaults" and "isolateReads" in
# ~/.claude/oracle-tenant-map.json -> ORACLE_TENANT_ID stays unset -> sees all
# tenants, exactly as before. Never fails the launcher.
if [ -z "${ORACLE_TENANT_ID:-}" ]; then
  _t="$("$BUN" /home/chillox-intern/.claude/oracle-tenant-read.ts "$PWD" 2>/dev/null || true)"
  [ -n "$_t" ] && export ORACLE_TENANT_ID="$_t"
fi
if command -v systemd-run >/dev/null 2>&1 && systemd-run --user --scope -q true 2>/dev/null; then
  exec systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=512M "$BUN" run "$APP"
fi
# Fallback (no user manager reachable): run uncapped rather than break MCP.
exec "$BUN" run "$APP"
