# oracle-skills

Central catalog + mechanism for **soulbrew oracles auto-creating skills** —
Hermes-style autonomous skill capture (the auto half; no `/learn`).

An oracle, at the end of a task, self-judges four triggers (complex task /
error recovery / user correction / reusable workflow) and, on a hit, saves the
procedure as a reusable Claude Code skill — non-blocking, with provenance, no
silent clobber.

## Layout

```
oracle-skills/
├─ auto-skill/            # THE MECHANISM (drop into an oracle's .claude/skills/)
│  ├─ SKILL.md            #   docs + manual usage
│  ├─ skill-discipline.md #   prose block to paste into an oracle's CLAUDE.md (the trigger logic)
│  ├─ scripts/
│  │  └─ auto_skill.py    #   non-blocking writer: create / validate / list (+ stage, dedup)
│  └─ tests/
│     └─ test_auto_skill.py   # 33 tests
└─ skills/                # THE CATALOG — auto-created skills land here (grows over time)
```

## How it works (two parts)

- **A — trigger (prose):** `auto-skill/skill-discipline.md` goes into an oracle's
  `CLAUDE.md` (always-on). The oracle self-judges the 4 triggers and calls the writer.
- **C — writer:** `auto-skill/scripts/auto_skill.py` writes the SKILL.md. It is
  non-blocking (safe in unattended worker panes), stamps provenance
  (`installer`, `created_at`, `trigger`, `created_by`), refuses a same-name /
  different-content clobber, and supports a `--stage` review gate.

## Writer usage

```bash
S=auto-skill/scripts/auto_skill.py
python3 $S create --name <kebab> --desc "one line" \
  --trigger reusable-workflow --source <oracle-id> --body-file /tmp/x.SKILL.md
python3 $S validate <path/to/SKILL.md>
python3 $S list
```

`--source` (creator) is mandatory — or set `AUTO_SKILL_SOURCE`. Landing dir:
`--dir` > `--global` > `$AUTO_SKILL_DIR` > `<cwd>/.claude/skills`.

## Merge / sharing model

- Every oracle contributes skills into `skills/`; a single committer pushes them
  in (no per-oracle branch/merge ceremony — hard conflicts are rare and the
  writer already prevents silent clobber).
- Merge mode is `local` by default (fast, offline; batch-push for backup),
  switchable to `online` (PR review) via config.

## Status

- **Built + tested:** the `auto-skill/` mechanism (writer + prose + 33 tests).
- **Empty for now:** `skills/` — fills as oracles run.
- **Not yet built / deferred:** category grouping in the writer, a Stop-hook
  (background review), cross-oracle dedup automation, `edit`/`patch` actions.
