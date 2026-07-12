---
name: auto-skill
description: Autonomous skill capture (Hermes-style) — self-judge 4 triggers at end of a task and save reusable procedures via a non-blocking writer. Use to inspect, validate, or manually run the auto-skill mechanism, or to review staged skills.
installer: hand-authored
---

# /auto-skill — autonomous skill capture (Hermes-style)

Makes soulbrew agents create reusable skills **on their own** when a task is worth
remembering — the autonomous half of Hermes' skill system, minus `/learn`.

Two parts:

- **Mechanism A (prose):** [`skill-discipline.md`](skill-discipline.md) — an
  always-on block for an agent's `CLAUDE.md`. It tells the agent to self-judge
  four triggers (complex task · error recovery · user correction · reusable
  workflow) at the end of each task and, on a hit, call the writer non-blocking.
- **Mechanism C (writer):** [`scripts/auto_skill.py`](scripts/auto_skill.py) — a
  deterministic, non-interactive writer. No blocking prompt (safe in unattended
  worker panes), stamps provenance, refuses silent name clobber, lands local by
  default, and supports a `--stage` review gate.

## Manual usage

```bash
S=.claude/skills/auto-skill/scripts/auto_skill.py

# create a skill (lands in ~/.claude/skills global by default; --source required)
python3 $S create --name deploy-fly --desc "Deploy to Fly.io" \
  --trigger reusable-workflow --source foreman-oracle \
  --body-file /tmp/deploy-fly.SKILL.md

# stage for review instead of going live (unattended workers)
python3 $S create --name x --desc "..." --stage

# validate a SKILL.md is well-formed
python3 $S validate .claude/skills/deploy-fly/SKILL.md

# list only auto-created skills (for cleanup/inspection)
python3 $S list
```

## Status / behaviors

| status | meaning | exit |
|---|---|---|
| `created` | written, live immediately | 0 |
| `staged` | parked in `.pending-skills/` for review | 0 |
| `exists-identical` | same skill already present, no-op | 0 |
| `refused-conflict` | name exists with different content — pick a new name or `--force` | 2 |
| `invalid` | bad name / empty desc / bad trigger | 2 |

## Deploy (turn it on for an agent)

Paste the contents of `skill-discipline.md` into the target agent's `CLAUDE.md`
(per-oracle repo, or a workspace-root `CLAUDE.md`). Adjust the script path in the
block if the `auto-skill` folder is not at `.claude/skills/auto-skill`.

Set two env vars for that oracle:
- `AUTO_SKILL_DIR` — override the landing dir (default is `~/.claude/skills`, global,
  so skills show in the Skills panel). Precedence: `--dir` > `--global` >
  `$AUTO_SKILL_DIR` > `~/.claude/skills` (global default).
- `AUTO_SKILL_SOURCE` — the oracle's id, stamped into every skill as `created_by:`.
  Creation is REFUSED if neither this nor `--source` is provided (no anonymous skills).

## Tests

```bash
python3 .claude/skills/auto-skill/tests/test_auto_skill.py
```

## Not yet in scope (deferred)

- **Mechanism B** (a Stop-hook that reads the session transcript and nudges the
  agent) — this v1 relies on the agent self-judging via the prose.
- **Cross-oracle dedup / a shared review queue** for the full unattended fleet.
- `edit` / `patch` of existing skills (writer does create/stage/validate/list).

---

ARGUMENTS: $ARGUMENTS
