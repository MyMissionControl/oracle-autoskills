---
name: audit-own-tools-for-context-waste
description: 'Use when auditing whether the tools you ship waste an agent''s context: score ceilings/silent-empty/silent-truncation, then rank by hit rate measured from real usage logs.'
installer: auto-skill
created_at: 2026-08-11T16:20:44+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'opus5-main'
category: 'harness'
content_hash: a913532ab22d1fbc26e5c2b4352f153b8150b53ed166cf67ea1f9348b810e732
---
# Audit your own tools for context waste

Use when someone asks "can we apply these read-tool / harness-engineering lessons to us?", or when
auditing whether the tools *you ship* (MCP handlers, CLI verbs, hooks, prompt assemblers) waste an
agent's context window. The trap is answering by restating the checklist. Answer with `file:line` +
a measured hit rate instead.

## Step 1 — enumerate only real surfaces

List every place **your** bytes enter a model's context. Nothing else counts:
- MCP/tool handlers that serialize a response
- CLI verbs whose stdout gets pasted into an agent pane
- prompt assemblers (`--system-prompt-file`, wake/spawn prompts, heredoc briefs)
- transcript / log readers that a UI or a headless `-p` call feeds back

Explicitly exclude the host agent's own built-in read/grep tools — you do not own them, and proposing
changes there is wasted work.

## Step 2 — the checklist

For each surface, ask:
1. **Three ceilings, not one** — line window, byte budget, AND per-line clamp. The third is the one
   everyone skips: one minified/base64 line fits the line window and eats the whole byte budget.
2. **Never return silence** — a bare `[]`/`""` is indistinguishable from a broken tool, so the model
   re-queries, widens, then abandons your tool. Every dead end must name itself *and* its recovery.
3. **Disclose truncation** — a cut with no `truncated` flag, no original length, and no pointer to the
   full text is a fragment the model cannot tell is a fragment. Precompute the resume offset so the
   model never does pagination arithmetic in reasoning tokens.
4. **Facts are not errors** — "not found", "already up to date", "no sprint yet" must not carry an
   `Error:` prefix / `isError:true` / non-zero exit, or the model apologises and retries.
5. **Relational invariants** — a ledger of what the model has SEEN + a writer that refuses partial
   overwrites can deadlock; a cache whose stale hit points at a compacted tool result must expire on
   use. No schema check catches these.
6. **Repair inputs, don't bounce them** — normalize aliases and whitespace, coerce numeric strings with
   `Number()` never `parseInt` (`"2abc"` must be rejected, not read as `2`), reject fractional offsets.
   When you must refuse, echo a *repaired candidate* so the retry is one edit, not one guess.
7. **Binary / device / unicode** — sniff magic bytes not extensions; refuse `/dev/zero`, `/dev/urandom`,
   `/proc/<pid>/fd/*` by name before any i/o; retry NFD/NFC and curly-quote spellings of a path.
8. **Asymmetry smell** — if an HTTP route clamps a param but the agent-facing handler for the same
   query does not, the guarded path serves the browser and the unguarded one serves the model. Always
   `grep` for the sibling.

## Step 3 — verify, and rank by hit rate not severity

This is the step that makes the audit worth anything. For every candidate finding:
- **Re-open the cited line.** Auditors invent line numbers and quote code that is not there.
- **Search the whole call path for the ceiling you claim is missing** — a caller, a shared helper, an
  env default, or the harness's own output cap may already provide it. If it does, the finding dies.
- **Measure who actually calls it**, from artifacts that record real traffic:
  - the tool's own usage table / log (e.g. a `*_log` table: how many calls, how many returned 0 rows)
  - agent transcripts: mine `tool_use`/`tool_result` pairs for that command and count `status:invalid`
    or error results — a 30% bounce rate is a finding; a never-executed path is not
  - the real corpus, not a fixture: measure the p50/p90/max size of the files the code actually reads
- Replay the hot loop yourself to get wall-clock and peak RSS instead of estimating them.

Rank by (waste per occurrence) x (measured frequency). A cheap fix with no behaviour change on
existing inputs clears the bar even at low frequency — but say so explicitly, and never dismiss an
item *only* because it has not been observed yet.

## Step 4 — report

Per surviving item: one line, `file:line`, the measured number, the smallest fix, and which checklist
item it maps to. Keep a separate **REFUTED — do not re-propose** list with the reason each died; that
list is what stops the same audit being re-run next quarter.
