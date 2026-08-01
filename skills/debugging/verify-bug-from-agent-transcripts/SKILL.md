---
name: verify-bug-from-agent-transcripts
description: Use before fixing a bug reported by an audit sweep, subagent, or earlier note about an agent run. Confirm the mechanism from raw .jsonl transcripts first; retract if refuted.
installer: auto-skill
created_at: 2026-08-01T23:16:01+07:00
created_session: 
trigger: reusable-workflow
created_by: claude-main
category: debugging
content_hash: 28d3939395a71d1c6146e7be13ff745f42470dbd86edf44693f1b9fcfa3d5e09
---
# Verify a reported bug against agent transcripts before fixing it

Use when a report (audit sweep, subagent, teammate, your own earlier note) claims an agent-run bug
and you are about to write code for it. Reports name a *mechanism*; transcripts hold the *receipt*.
Shipping a fix for an unverified mechanism is how a wrong diagnosis becomes permanent code.

## Steps

1. **Turn the claim into a literal string that must exist on disk.** Not "oracle_learn collides" —
   the error text (`already exists`), the filename, the exit code, the verb name.
   No such string can be named → the claim is an inference, treat it as unverified.

2. **Grep the raw transcripts, not summaries.**
   `~/.claude/projects/<slug>/<session-uuid>.jsonl` — one JSON object per line.
   The payload lives in `tool_result` entries with `"is_error": true`.

   ```bash
   python3 - <<'PY'
   import json,glob,re
   for f in glob.glob('<HOME>/.claude/projects/*<agent-or-project>*/*.jsonl'):
       for ln in open(f,encoding='utf-8',errors='replace'):
           if '<literal string>' not in ln: continue
           s=json.dumps(json.loads(ln),ensure_ascii=False)
           for m in re.finditer(r'.{120}<literal string>.{100}', s):
               print(f.split('/')[-2], '|', m.group(0).replace('\\n',' '))
   PY
   ```
   Plain `grep -oE '.{100}<string>.{80}'` on the .jsonl works too and is faster for one-off checks.

3. **Read the surrounding evidence, not just the hit count.** Filenames, timestamps and ids in the
   error usually reveal the real mechanism — and often show it came from a *different* run than the
   report claimed. Correct the attribution even when the bug itself is real.

4. **Cross-check the mechanism in the dependency's source** before writing the fix. A collision
   claim dies if the writer already auto-suffixes; a truncation claim needs the actual constant.
   `grep -rn 'slice(0,\|substring(0,\|already exists' <dep>/src --include=*.ts | grep -v __tests__`

5. **Decide explicitly, and record it:**
   - confirmed → fix, and put the receipt (error string / filename) in the test-file header comment
     so the next reader cannot re-litigate it
   - refuted → retract it out loud to whoever received the report; do not silently drop it
   - unverifiable → say "mechanism not confirmed" and do not ship a fix built on it

## Why this order

A report you cannot reproduce is a hypothesis. Fixing a hypothesis produces code whose only
justification is a sentence someone wrote — the same failure mode as a gate that lives in prose.
The receipt is what makes the fix reviewable a month later.
