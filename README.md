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
│     └─ test_auto_skill.py   # 37 tests
├─ tools/                 # FLEET OPS — run by the single committer (orchestrator)
│  ├─ collect_commit.py   #   gather oracle skills -> dedup/rename -> ONE commit -> push (local|online)
│  ├─ sync_skills.py      #   central skills -> ~/.claude/skills (flattened, archive-removed)
│  └─ tests/test_v2.py    #   17 tests (collect + sync end to end)
└─ skills/                # THE CATALOG — auto-created skills land here (grows over time),
                          #   organized skills/<category>/<name>/ (flattened on sync)
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

- **Built + tested (54 tests):** the `auto-skill/` mechanism (writer + prose, 37)
  and the `tools/` fleet ops (collect_commit + sync_skills, 17). The writer stamps
  `category:`; collect_commit organizes by category + dedups (rename on collision);
  sync_skills flattens into `~/.claude/skills` and archives removed skills.
- **Empty for now:** `skills/` — fills as oracles run.
- **Not yet wired (gated):** deploying the `skill-discipline.md` prose into a live
  oracle's CLAUDE.md + setting `AUTO_SKILL_DIR` / `AUTO_SKILL_SOURCE` per oracle.
- **Deferred:** a Stop-hook (background review, mechanism B), automatic online-PR
  review flow, `edit`/`patch` actions.
