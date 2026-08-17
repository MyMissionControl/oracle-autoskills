---
name: attribute-doc-retrieval-mechanism
description: 'Use when asked what mechanism actually surfaces a stored doc/note into an agent''s answer, or before optimizing a retrieval layer: attribute it from transcripts, including zero-tool-call…'
installer: auto-skill
created_at: 2026-08-17T11:34:24+07:00
created_session: 
trigger: 'complex-task'
created_by: 'subagent'
category: 'forensics'
content_hash: c0c9283e70092ae1e9354d53d2b3986373332984b8d53695b61e25c206968dac
---
# Attribute which mechanism surfaced a stored doc into an agent's answer

Use when asked "what actually pulls an old doc/note into the answer?" across agent
transcripts (`~/.claude/projects/**/*.jsonl`), or before optimizing a retrieval layer.
The trap: the winning mechanism leaves **no tool call**, so counting tool calls ranks it zero.

## 1. Never `cat` the corpus
Prefilter raw lines by substring before `json.loads`; only then parse.
`if '"tool_use"' not in line and '"text"' not in line: continue`
~850MB scans in <10s this way. Filter the window by **record `timestamp`**, not file mtime —
mtime counts sessions that merely got touched.

## 2. Reconcile before trusting the classifier
A raw `grep -oh '"file_path":"[^"]*\.md"' | wc -l` counts Read **plus** Write/Edit.
Split by tool name and make the numbers meet exactly, or your ranking is wrong.

## 3. Split retrieval from writes
Memory/knowledge MCP servers are usually **write-dominated**. Bucket tool names into
READ vs WRITE sets explicitly. Reporting "N MCP calls" as retrieval is the classic error.

## 4. The system prompt is NOT in the transcript
Auto-injected context (index files, ancestor config files, SessionStart hook output) never
appears in the .jsonl. You cannot count it directly. Prove it by **differential**:

- Build the slug set from the store's own directory listing.
- Regex assistant `text` blocks for those slugs.
- For each hit, ask: was that exact file `Read` earlier in the *same* session?
- **cited but never read** = the auto-injected index carried the payload.
- Clinch it with **timestamp ordering**: if the only explicit read of the index came
  *after* the citation, injection is the sole possible source.
- Drop slugs that collide with real repo/dir names — they are false positives.

## 5. Enumerate hooks; they are a hidden mechanism
Read the launcher config (`settings.json` → `hooks.SessionStart`) and **run each hook**
with a synthetic payload to see what it emits and measure its bytes. Hooks that inject
files only for certain repos emit 0 bytes elsewhere and look dead. Read the hook source —
a shell `grep` over it may be rewritten by another hook, so use the Read tool.

## 6. Separate "old knowledge" from "what this run just wrote"
Track paths Written/Edited earlier in the same session; a later Read of those is
**self-echo**, not retrieval. Workflow scratch docs otherwise dominate the ranking.
Also split skill-body files out of "doc reads" — those belong to the skill mechanism.

## 7. Measure search waste as episodes, not raw reads
Episode = a search (Grep/Glob/rg) followed by Reads, closed by any other tool.
Report distinct target files per episode: **median and p90**, not just mean.
Mean near 1.1 with median 1 means there is no "read the wrong files first" waste to remove —
say so plainly instead of proposing an optimization.

## Report shape
Per mechanism: events, distinct sessions, and bytes for the zero-tool-call ones.
State plainly which mechanism costs zero tool calls — that is usually the answer.
