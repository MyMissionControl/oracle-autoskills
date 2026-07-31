---
name: audit-revert-agent-file-edits
description: Use when a non-git file was changed by a Claude/SDK agent and you must count/explain the edits or revert to the pre-edit state — mine ~/.claude/projects transcripts (dedup by tool_use id) + fs mtime.
installer: auto-skill
created_at: 2026-07-31T08:06:45+07:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: forensics
content_hash: d848886da5bf5f2a540a93780d1228ed44479b52c2094c0d09c0e1e97cea1973
---
# Audit / revert an agent's edits to a non-git-tracked file (via Claude transcripts + mtime)

**When:** a file `<F>` that is NOT in git was changed by a Claude Code / SDK agent (oracle, orches worker, etc.), and you must answer "how many times / why was it edited?" or "revert it to before the agent touched it." Git history is unavailable, so the Claude transcripts + filesystem are the only ground truth.

## Steps

1. **Confirm it's not git-tracked** — `git -C <dir> log -- <F>`. If tracked, use git and stop here.

2. **Search ALL project transcripts, not just the obvious one** — the agent may have run under a different cwd/project slug than the file's directory. Parse every `~/.claude/projects/*/*.jsonl` line as JSON; collect `tool_use` blocks where `name ∈ {Edit,Write,MultiEdit}` and `input.file_path == <abs path of F>` (match the EXACT absolute path — the basename alone is often common, e.g. `req.md`).
   - **Dedup by the tool_use `id`** (`toolu_...`). Resumed/compacted sessions copy prior history forward across files → naive counting double-counts. One unique `id` = one real operation.
   - Bash `cat`/`grep`/`head` reads are NOT edits — ignore them; only Edit/Write/MultiEdit mutate.

3. **Create vs overwrite** — read each Write's `tool_result`: `"has been created"` = new file; `"has been updated"`/overwritten = pre-existing. Also check for a `Read` of `<F>` shortly BEFORE the Write → confirms the file pre-existed (the agent read it, then clobbered it).

4. **Recover the pre-edit content** — it lives in the `tool_result` of the `Read` that immediately preceded the overwriting Write. Extract that result and strip the `cat -n` prefixes (`^\s*\d+\t`) to rebuild the raw file.

5. **Validate losslessness** — Claude Code's Read truncates any single line longer than ~2000 chars. If any reconstructed line is ≥ ~1990 chars, the recovery may be truncated → find another source instead of trusting it.

6. **Cross-check** — `find <roots> -iname '<basename>'` for sibling copies; compare byte sizes (a 1-byte gap is usually a trailing newline). And compare `<F>`'s filesystem **mtime** to the Write's timestamp: if they match and there was exactly one Write, the file is provably untouched since → your count is authoritative regardless of any un-logged writer.

7. **Revert safely** — back up the current version to a scratch path FIRST (never discard it), then write the recovered original back. Verify: byte size matches the recovered source AND `grep -c` for the agent's added markers returns 0.

## Gotchas
- `len()` on a Python str counts characters, not bytes — Thai/UTF-8 inflates byte size ~3x; measure bytes with `.encode()` / `os.path.getsize` when comparing to disk.
- Print-time `+"\n"` can make a reported size 1 byte larger than what was actually written to disk — compare the file on disk, not a debug print.
- SDK agents that don't run through the Claude Code CLI may not log to `~/.claude/projects` at all — but the filesystem mtime still bounds "last modified," so lean on it as the independent check.
