# rules/ — fleet-wide oracle rules, in tiers

One rule, one place. Spec: `soulbrew/docs/oracle-rule-tiers-spec.md`.

| tier | file | reaches context via | who gets it |
|---|---|---|---|
| 0 workspace map | `soulbrew/CLAUDE.md` | native auto-load of every ancestor dir | everything under soulbrew |
| 1 universal | `universal.md` | `inject_rules.py` (SessionStart hook) | every oracle |
| 2 role | `role-orchestrator.md` · `role-worker.md` | same hook, role from `roles.json` | that role only |
| 3 self | `<oracle>/CLAUDE.md` | native auto-load | that oracle only |

## Why a hook and not a shared file

A project `CLAUDE.md` `@import` cannot reach outside its own repo. Probed 2026-08-14: `@../rules/x.md`,
`@/abs/path/x.md`, `@~/.claude/x.md`, and a symlink pointing outside the repo **all fail to load** —
only paths at or below the repo work, and imports written in an *ancestor* `CLAUDE.md` do not resolve
either. So tiers 1 and 2 cannot be shared by import or symlink.

A SessionStart hook reads any absolute path and is launcher-independent, so the same text lands whether
the session was started by `maw wake`, the MissionControl Team-up button, or `/orches`.

## Wiring

```jsonc
// ~/.claude/settings.json  →  hooks.SessionStart[]
{ "type": "command",
  "command": "python3 <this-dir>/inject_rules.py" }
```

Non-oracle sessions emit nothing and pay zero tokens. An oracle is identified by its repo dir name
ending in `-oracle`, or by an explicit key in `roles.json` — deliberately **not** by looking for a `ψ/`
dir, because the shared soulbrew vault has one too and every workspace-root session would be swept in.

The last line of the injected text is a receipt:

```
[rules] foreman · universal + role-orchestrator · 5434 bytes · /path/to/rules
```

A missing rules file becomes `[rules] MISSING role-x.md` in the context rather than silently shipping
fewer rules — a broken hook must not look identical to a working one.

## Adding an oracle

Add `"<name>": "worker"` (or `"orchestrator"`) to `roles.json`. An oracle that is not listed falls back
to `_default` (`worker`) — never to orchestrator.

## Tests

```
python3 tests/test_inject_rules.py                    # 22 checks, stdlib only
python3 tests/check_oracle_files.py                   # drift report (exit 0)
python3 tests/check_oracle_files.py --strict          # gate: fails while tier-1 text is still inline
```

`check_oracle_files.py` stays report-only by default so a fresh clone with un-cleaned oracle files does
not fail; **as of 2026-08-14 the fleet is clean and `--strict` passes 5/5**, so wire the `--strict` form
into any gate that guards these files.

## Status

Live since 2026-08-14. The hook is registered in `~/.claude/settings.json` (backup:
`settings.json.bak-rules-hook-*`) and all five oracle `CLAUDE.md` files are identity-only. Verified: a
global SessionStart hook **merges with** a project-level one rather than replacing it (probed with a
fixture oracle carrying its own `.claude/settings.json` — both fired), and running the real hook with
each oracle repo as cwd yields `role-orchestrator` for foreman and `role-worker` for the rest.

Injected size: 5,435 B for the orchestrator, 4,715 B for a worker. Own files shrank
3,004→1,180 (foreman), 2,843→660 (bob), 2,297→663 (jack), 3,005→1,108 (john), 3,004→1,107 (mike).
