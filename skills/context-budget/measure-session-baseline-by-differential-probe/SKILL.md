---
name: measure-session-baseline-by-differential-probe
description: 'Use when asked what an agent''s session-start context costs, or which config knob is worth turning off — measure each component by differential headless probes, not file bytes.'
installer: auto-skill
created_at: 2026-08-14T15:55:39+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'context-budget'
content_hash: 565971bb0a09cb8066d177b36cecd270df134951f3d25564b9546ee558bce943
---
---
name: measure-session-baseline-by-differential-probe
description: Use when asked what an agent's session-start context costs, or which config knob is worth turning off — measure each component by differential headless probes instead of estimating from file bytes.
---

# Measure session baseline by differential probe

File bytes lie. A component's real cost is the **delta between two otherwise-identical
sessions**, one with it and one without. Three probes settle a whole config surface in
a few minutes and cost ~4 cheap requests.

## Setup: a throwaway project dir

```bash
SP=<scratchpad>/probe-<suffix>        # suffix must match the dir-name test your hooks use
mkdir -p $SP && cp <real-project>/AGENT_CONTEXT.md $SP/   # keep the project file realistic
```

Naming matters: SessionStart hooks often gate on the directory name (`*-oracle`,
`*-worker`). A wrongly-named probe silently skips the hook you meant to measure.

## Probe A — baseline

```bash
cd $SP && claude -p "say ok" --effort low
```

Read the prefix from the transcript, not from any UI:

```python
# newest *.jsonl under ~/.claude/projects/<slugified-cwd>/
u = first record with type=="assistant" and message.usage
prefix = u.input_tokens + u.cache_creation_input_tokens + u.cache_read_input_tokens
```

`cache_read` is a real part of the prefix — include it or every probe after the first
reads ~40% too low.

## Probe B — one component removed, everything else byte-identical

The trick for config-dir-scoped components (global skill/prompt libraries): build a
mirror config dir of **symlinks to every entry except the one under test**, so hooks,
settings, plugins and credentials stay identical.

```bash
mkdir -p $SP/cfgB/<component-dir>          # empty replacement
for f in $CONFIG_DIR/* $CONFIG_DIR/.credentials.json; do
  n=$(basename "$f"); [ "$n" = "<component-dir>" ] && continue
  ln -sfn "$f" $SP/cfgB/"$n"
done
CLAUDE_CONFIG_DIR=$SP/cfgB claude -p "say ok" --effort low
```

Gotcha: symlinking the transcripts/`projects` dir means both probes write to the **same**
transcript folder — good (one place to read), but distinguish runs by mtime, not by path.

## Probe C / D — per-project and CLI-flag knobs

```bash
echo '{"<pluginToggleKey>":{"<plugin>":false}}' > $SP/.<agent>/settings.json   # C
claude -p "say ok" --effort low --strict-mcp-config                            # D: no MCP
```

Probe C also answers a second question for free: **does this knob even work at project
scope?** A zero delta means the setting is global-only — worth knowing before designing
per-role profiles around it.

## Report as a subtraction table

| component | tokens | how measured |
|---|---|---|
| library listing | A − B | config-dir mirror |
| plugin | A − C | project-scope toggle |
| external tool servers | A − D | CLI flag |
| irreducible base | D − (deltas) | remainder |

State the remainder explicitly. The floor (system prompt + tool schemas) is usually the
largest single block and is **not** configurable — a report that omits it invites a
redesign chasing savings that cannot exist.

## Before recommending a cut

Rank buckets by tokens, then strike out every bucket whose text is a **routing signal**
the model needs to decide when to act (tool/skill descriptions). Those are usually the
heaviest bucket, and cutting them trades quality for tokens. Say so in the same table
rather than reporting the raw ceiling as achievable savings.
