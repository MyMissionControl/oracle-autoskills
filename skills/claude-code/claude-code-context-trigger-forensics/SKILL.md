---
name: claude-code-context-trigger-forensics
description: Use when a Claude Code statusLine/context tool drifts from the native auto-compact %, or to find the real auto-compact trigger by mining transcript compactMetadata preTokens.
installer: auto-skill
created_at: 2026-07-22T08:56:31+00:00
created_session: 
trigger: error-recovery
created_by: claude
category: claude-code
content_hash: 8562ce1ed351b46163b14b1c7e73b4151efe07b26d2e37ca49e2373999c7e257
---
# Claude Code context/auto-compact forensics

Use when a Claude Code `statusLine` or context-tracking tool's % drifts from the native "% until auto-compact" indicator, or when you need Claude Code's REAL auto-compact trigger point (do not trust reverse-engineered formulas — the `autoCompactWindow` setting can be capped/ignored by newer versions).

## 1. Capture the real statusLine stdin JSON (know the true schema)
A `statusLine` command runs fresh on every refresh (no restart needed to change it). Temporarily tee its stdin to a file:
- In the script's stdin handler, right after reading `raw`, add: `writeFileSync("<abs tmp path>", raw)` (import writeFileSync). Wrap in try/catch; do NOT alter what's printed.
- Wait a few seconds for a refresh (only actively-updating panes re-invoke it), then read the file. Revert the edit.
- Recent Claude Code exposes `context_window.{total_input_tokens, context_window_size, used_percentage, remaining_percentage, current_usage}` + `exceeds_200k_tokens`, `transcript_path`, `model.id`, etc. `used_percentage` is against the RAW window and there is NO field for the auto-compact trigger — you must derive it (see step 2/3).

## 2. Find the REAL auto-compact trigger empirically (don't compute it)
Claude writes a tiny (~1KB) system line at each compaction with `compactMetadata: {trigger, preTokens, postTokens}`. Mine `~/.claude/projects/**/*.jsonl`:
- Parse `compactMetadata.preTokens` where `compactMetadata.trigger === "auto"` (IGNORE `"manual"` — those fire at arbitrary points and pollute the number).
- Correlate with `timestamp` + model; the most-recent auto `preTokens` is the true 100% point. Cluster the last ~12 to confirm stability.
- Cross-check the session's resolved `autoCompactWindow` (walk cwd → $HOME → global settings.json) against `preTokens + reserve`. If they disagree (e.g. setting says 700K but preTokens ≈ 267K), the setting is being clamped/ignored — trust `preTokens`.

## 3. Self-calibrate the tool (pull the real number every refresh)
Instead of `min(window, autoCompactWindow) − reserve`, read the last `trigger:"auto"` `preTokens` from a BOUNDED tail (~1 MiB via openSync+readSync, not full-file — memory-safe across many panes) of the session's own `transcript_path`; cache it to a small global file so fresh sessions inherit it; keep the formula only as a last-resort fallback. This tracks Claude's actual behavior and self-corrects if it changes. Split the pure parser out and unit-test it (tolerate a truncated first line from the tail slice).

## Gotchas
- The compaction marker sits at EOF only right after a compaction; mid-session it's far back — that's why the global cache carries it between compactions.
- Raw transcript JSON is compact (`"trigger":"auto"`, no space) even though `json.dumps` shows spaces — match value tokens, not colon spacing.
