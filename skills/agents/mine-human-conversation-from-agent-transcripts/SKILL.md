---
name: mine-human-conversation-from-agent-transcripts
description: 'Use when feeding a memory/search store from agent session .jsonl transcripts, or when an existing capture files useless entries: record shapes, hook choice, memory bound.'
installer: auto-skill
created_at: 2026-09-01T21:49:44+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'agents'
content_hash: 75f9b67dd2ac4a40badd3efb30fa76dd9498e1012f8c4b0e4ecb5a847eda315c
---
# Mine the human conversation out of agent session transcripts

Use when wiring "remember what we discussed" for an agent CLI: a memory/search store
must be fed from session transcripts (`.jsonl`), or an existing capture feature files
useless entries.

## 1. Check whether a capture feature already exists — and whether it ever ran

Grep the agent/runtime repo for `.jsonl`, `transcript`, `capture`, `sweep`. Features
like this ship **opt-in default-off** and then sit dead for months. Proof it never ran
is its **state file**: `ls <data-dir>/*capture*.json` — no file = zero captures ever.
Also check the enabling env var appears in the settings/profile, and that a hook is
actually registered. "Code exists" is not "feature runs".

## 2. Judge the existing extractor by DRY-RUNNING it, never by reading it

Import its miner, pass a REAL transcript, print what it would store, write nothing:

```ts
import { mineX } from '<repo>/src/<capture>.ts';
const mined = mineX(process.argv[2], 12);
for (const m of mined.moments) console.log(`[${m.kind}] ${m.text.slice(0,150)}`);
```

Score it against the actual goal. Keyword-gated miners typically fail three ways at once:
tool OUTPUT dominates (it looks like conversation in the record stream), a non-English
user is invisible (English-only regex), and `break` at N keeps the START of the session
while the conclusions are at the END.

## 3. Learn the record shapes before writing a filter — they are not uniform

Count them; do not assume. On one real transcript:

- `type:user` + `content:[tool_result]` = command output, **not a person** (49 of 52)
- `type:user` + `content:[{type:'text'}]` = the person (GUI/extension sessions)
- **`content` can be a bare STRING** — headless (`-p`) and SDK sessions record the human
  prompt that way. Checking only `Array.isArray(content)` silently drops them all.
- `isMeta:true` = skill/system text injected as a user turn — skip
- `isSidechain:true` = subagent chatter — skip
- The human's DECISIONS live in the `tool_result` of the question/choice tool; map its
  `tool_use.id` from the preceding assistant record, and strip the harness boilerplate
  the runtime appends to every such result.
- Automation-driven panes usually have **no** human text record at all, so a
  "no human turn -> skip" guard filters them for free. Verify with a census across the
  corpus before assuming.

## 4. Pick the hook event by SEMANTICS, not by name

`Stop`-style events fire at the end of **every turn**, so a content-hash dedup still
files a fresh, ever-growing entry each turn. Prefer a genuine `SessionEnd`. Prove it
with one throwaway headless run whose hook dumps stdin to a file — that also confirms
which fields (transcript path, session id, cwd) the payload actually carries.

## 5. Build the extractor with a red-proof for the memory bound

Read the transcript **line by line**; a whole-file read costs ~3x the file size in RSS
(163 MB file measured at 537 MB). Write the test that generates a >100 MB fixture and
asserts RSS growth stays small, then **mutate the reader back to a whole-file read and
watch the test go red** — otherwise the bound is untested. Keep every human turn, keep
every decision, keep only the TAIL of the assistant prose, and clip per turn.

## 6. Make silence detectable

Append one line per invocation — skips included — to a log next to the store. A capture
hook that quietly stops firing is indistinguishable from a run of quiet sessions; that
is exactly how the dead feature in step 1 went unnoticed.

## 7. Do not edit a read-only/vendored engine to fix its extractor

Write your own extractor in a repo you own and **import** the engine's persistence
function unchanged, so entries land in the same store, indexed the same way.

## Verify before claiming it works

Run a real headless session with the store's env vars redirected to a sandbox dir. The
hook fires with the real global config, and the entry lands in the sandbox — proving the
wiring without polluting the real store. Also confirm whether a per-session
`--settings`-style file MERGES with or REPLACES global hooks; measured MERGE on one
runtime, but re-check per version.
