---
name: recover-truncated-agent-task-payload
description: 'Use when a subagent''s task prompt arrives with its JSON/data payload truncated or mangled: recover the real assignment from the orchestrator''s session transcript and scratchpad instead of guessing.'
installer: auto-skill
created_at: 2026-08-17T14:14:44+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'memory-index-rewrite-batch-1'
category: 'agents'
content_hash: 9086bdebd072caa8d9c848873e3edca5177e9fa32bbf504f67392d3809e89e39
---
# Recover a truncated subagent task payload

Use when a subagent's prompt arrives with its data payload mangled or cut off — e.g. the task
says "YOUR 10 ENTRIES (JSON)" but only a fragment like `,{"i":7,"f` survives. Do NOT guess the
assignment: the orchestrator's own state is on disk, and guessing a batch corrupts the parent's
apply step (wrong index -> wrong line rewritten).

## Steps

1. **Salvage every identifier in the fragment.** A single surviving field (`"i":7`) is enough to
   locate the batch later. Note it before doing anything else.

2. **Find the orchestrator transcript.** Subagent prompts are recorded in the session JSONL under
   `~/.claude/projects/<slugified-cwd>/<session-id>.jsonl`. The session id is usually visible in
   your own scratchpad path (`/tmp/claude-*/<slug>/<session-id>/scratchpad`).

3. **Grep the transcript with python, not `grep -o`.** These files reach tens of MB and
   `grep -o '.\{0,4000\}'` backtracks for minutes. Instead:
   ```bash
   python3 -c "
   d=open('<session>.jsonl','rb').read().decode('utf-8','replace')
   j=d.find('<a distinctive phrase from your prompt>')
   print(d[j-9000:j+4000].replace('\\\\n','\n'))"
   ```
   Search for a phrase from the RULES/prose part of your prompt — that part survives even when the
   data payload does not.

4. **Read the orchestrator script, not just the prompt.** The printed region usually contains the
   dispatch code: the batch size, how batches are sliced (`for i+=BATCH; batches.push(all.slice(...))`),
   and — most valuable — the shell commands that BUILT the input. Those name a scratchpad file.

5. **Load that scratchpad file — it is the full, unmangled input.** Then locate your own batch by
   the identifier from step 1 and the slicing rule from step 4:
   ```bash
   python3 -c "
   import json; d=json.load(open('<payload>.json'))
   pos=[k for k,x in enumerate(d) if x['<idfield>']==<value>][0]
   print(json.dumps(d[pos//10*10:pos//10*10+10],ensure_ascii=False,indent=1))"
   ```
   `pos // BATCH` gives the batch index; contiguous slicing means one matching id pins the whole set.

6. **Sanity-check the recovered batch against the prompt's own description** (count matches the
   announced "YOUR N ENTRIES", the salvaged fragment appears in it, field names match the output
   schema). Only then start the real work.

## Notes

- Prefer recovery over inference every time. Two plausible readings of an index (absolute line
  number vs position within a filtered list) point at different records, and nothing in the
  fragment distinguishes them.
- If the transcript is genuinely unavailable, return a result for the entries you can prove are
  yours and state the ambiguity — do not silently widen the batch.
- Background a slow `grep -rl` over `$HOME` at most once; the targeted python scan of the single
  session file is what actually finds it.
