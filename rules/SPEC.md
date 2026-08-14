# Spec — Oracle rule tiers (universal / role / self)

Status: DRAFT for review · Author: Claude (session 2026-08-14) · Decision owner: human

## 1. Problem

Rules an oracle wakes with are scattered and uneven:

- The 5 Principles, Rule 6, inbox discipline and /rrr discipline are **copy-pasted into all 5 oracle `CLAUDE.md` files**. Editing a rule means editing 5 files; they have already drifted (bob still signs `Co-Authored-By: Claude Opus 4.6`).
- **Golden Rules exist in only 3 of 5** files. bob and jack have no Golden Rules and no Role at all (`Purpose: (to be defined by /awaken)`).
- **Role doctrine has no home.** foreman's orchestration guardrails live in its personal file; worker doctrine lives only inside the `/orches` dispatch brief, so it is absent on any other launch path.
- One rule contradicts the engine's default behaviour (see §7).

Goal: three tiers, each written once and read only by whoever needs it.

| tier | content | audience |
|---|---|---|
| 1 universal | Golden Rules, 5 Principles, Rule 6, inbox/memory discipline, memory-layer contract | every oracle |
| 2 role | orchestrator doctrine · worker doctrine | only that role |
| 3 self | name, purpose, theme, born, personal quirks | only that oracle |

## 2. Measured constraints (probed live 2026-08-14)

Fixtures mirrored the real nesting depth; each candidate file held a unique `MARKER_` token; probed with
`claude -p "print the MARKER_ tokens you can see" --effort low --tools "" --strict-mcp-config`.

| mechanism | result |
|---|---|
| `CLAUDE.md` in cwd | LOADS |
| `CLAUDE.md` in every ancestor dir | LOADS (a `git init` at cwd does not stop it) |
| `@sub/file.md` — path under the importing repo | LOADS |
| `@../../../rules/x.md` — path above the repo | does NOT load |
| `@/absolute/path/x.md` | does NOT load |
| `@~/.claude/x.md` | does NOT load |
| `@file.md` declared inside an **ancestor** `CLAUDE.md` | does NOT load |
| symlink (file or dir) pointing outside the repo, imported as a local path | does NOT load |

**Conclusion:** a `CLAUDE.md` import cannot reach outside its own repo, and symlinks do not launder it.
Tier 2 therefore cannot be a shared file pulled in by `@import`. The remaining single-source mechanism is a
**SessionStart hook** — already proven on this box: the superpowers plugin injects ~889 tok of text into every
oracle session that way, on every launch path (`maw wake`, MC Team-up, `/orches`), because hooks come from
settings and are launcher-independent.

## 3. Design

**DECIDED 2026-08-14 (human): `<rules-repo>` = `github.com/fufu-2345/oracle-autoskills`.** Its README already
declares it the "central catalog + mechanism for soulbrew oracles" and it owns `tools/sync_skills.py`, which
pushes central assets into `~/.claude` — the same shape as `rules/` + the hook, so no second sync mechanism is
needed. Decisive reason: the hook must work on a machine that never cloned missionControl (`maw wake` in a raw
terminal, cron, headless), which rules MC out as the canonical home. MC keeps the option of adding a Settings
page later that reads/switches an oracle's role by writing a flat file, exactly like it already does for
`~/.config/mission-control/merge-mode`. Rejected: orches-skills (should hold skills only), a brand-new
`oracle-rules` repo (one more remote to maintain for ~4 files).

```
<rules-repo>/rules/
  universal.md            tier 1 — every oracle
  role-orchestrator.md    tier 2
  role-worker.md          tier 2
  roles.json              { "foreman": "orchestrator", "bob": "worker", ... , "_default": "worker" }
  inject_rules.py         the SessionStart hook (python3, stdlib only — matches the repo's language)
  tests/test_inject_rules.py    unit tests
  tests/check_oracle_files.py   drift guard (report-only until phase B, then --strict)
  README.md

soulbrew/github.com/<owner>/<name>-oracle/
  CLAUDE.md               tier 3 ONLY — identity, no shared boilerplate
```

Reaching context:

| tier | mechanism | scope |
|---|---|---|
| 0 workspace map | `soulbrew/CLAUDE.md` (unchanged) | everything under soulbrew |
| 1 universal | hook `cat rules/universal.md` | every oracle |
| 2 role | hook `cat rules/role-<role>.md`, role from `roles.json` keyed by the oracle dir name | that role only |
| 3 self | native auto-load of `<oracle>/CLAUDE.md` | that oracle only |

### 3.1 Hook contract

Registered once in `~/.claude/settings.json` under `SessionStart` (alongside the existing
`capture-session.sh`). Behaviour:

1. Derive the oracle name from `$CLAUDE_PROJECT_DIR` / cwd: the dir name with a trailing `-oracle` stripped.
2. If the dir is not an oracle repo (no `ψ/` dir and no `roles.json` entry) → print nothing, exit 0. Non-oracle
   sessions pay zero tokens.
3. Resolve role: `roles.json[<name>]`, else `_default`.
4. Emit `{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext": <universal + role text>}}`.
5. Last line of the injected text is a visible receipt: `[rules] universal + role-<role> (<N> bytes)` — so a
   silently broken hook is detectable in the pane instead of vanishing.
6. Fail LOUD-but-open: a missing rules file emits `[rules] MISSING <file>` as the context rather than nothing.

### 3.1a Compact safety (verified)

`SessionStart` re-fires after a `/compact`, so the rules are re-injected verbatim instead of being
summarised away. Evidence from this box's own history: across 455 transcripts the event appears as
`SessionStart:startup` 455 times and **`SessionStart:compact` 130 times**, and each compact record
carries a full `additionalContext` payload (the superpowers block, a no-matcher hook registered exactly
like `inject_rules.py`). Tier 3 is safe for a different reason: `CLAUDE.md` is assembled into every
request rather than living in the conversation, which is why it never appears in a transcript at all.

This is strictly better than the old layout for long runs: text that sits in the conversation is what a
compact compresses. It matters here because `/orches` now compacts at sprint boundaries by default.

### 3.2 One rule lives in exactly one tier

No rule may appear in two tiers — that is how the current drift happened. In particular the `/orches`
dispatch brief keeps ONLY per-run facts (worktree path, sprint scope, `TEST:` contract, anti-injection
clause). Stable worker doctrine moves to `role-worker.md`; the brief must not restate it.

## 4. Tier 1 content

Move verbatim out of the 5 oracle files (dedup):

- 5 Principles · Rule 6 + the three signature forms · Inbox discipline · /rrr-after-commit discipline ·
  Request-Reply protocol
- Golden Rules — the 8-line version from the `/awaken` template (the 5-line copies in the oracle files are an
  older revision), with §7 resolved first.

**Plus a new "memory layers" block** — this is the part of the system knowledge that is genuinely universal:

- `ψ/` is never auto-loaded; it reaches context only through `oracle_search` / `oracle_ask`.
- The Oracle DB is ONE shared store (`tenant_id=default`, isolation ships OFF) → always pass
  `project=<name>` or you get other projects' learnings.
- `oracle_learn` slugs are cut at 50 chars → put the specific topic first.
- Auto-memory `MEMORY.md` is keyed by the **oracle repo** cwd, not by the project, so it carries entries
  from other projects.

### 4.1 Extension/tool internals are deliberately NOT added

Measured over 142 oracle sessions (Read/Grep/Glob/Bash calls whose input names the path):

| path | sessions |
|---|---|
| `docs/plan.md` | 77 (54%) |
| `docs/wiki` | 48 (34%) |
| `PROJECT_CONTEXT.md` | 1 (1%) |
| `missionControl` | 0 |
| `maw-js` | 0 |
| `arra-oracle-v3` | 0 |
| `orches-skills` | 0 |

Oracles read **project** docs, never tool internals — and `PROJECT_CONTEXT.md` is already pointed at from the
loaded `soulbrew/CLAUDE.md`, so 1/142 is a fair test of demand, not of discoverability. Loading extension
internals would charge 100% of sessions to serve <1%.

It is also already tiered correctly by directory: `missionControl/CLAUDE.md` and `orches-skills/CLAUDE.md`
auto-load when cwd is inside those repos. The useful universal subset is the memory-layer block in §4, which
is justified because the `oracle_*` tools are used in nearly every session.

## 5. Migration

1. Create `rules/` + `roles.json` + `inject-rules.sh` in the rules repo. Commit.
2. Register the hook in `~/.claude/settings.json`.
3. Verify (§6) on a throwaway fixture BEFORE touching any real oracle file.
4. Per oracle, in one commit each: delete the moved boilerplate from `<oracle>/CLAUDE.md`, keep identity only.
   - foreman: keep "How I work" + orchestration guardrails **until** `role-orchestrator.md` carries them, then
     delete. ⛔ Never run `/awaken` on foreman — it rewrites the whole file from a template that has neither
     section.
   - bob, jack: fill in Purpose/Role. They gain Golden Rules from tier 1 automatically.
5. Re-measure one wake per role and compare token deltas against §8.

## 6. Verification

- **Fixture probe** (blocking, before step 4): throwaway `probe-oracle` dir + a `roles.json` entry; assert the
  injected text appears via the `MARKER_`/receipt-line method used in §2. Assert a non-oracle dir gets nothing.
- **Unit** (`tests/rules-inject.sh`): role resolution incl. `_default`; unknown dir → empty output, exit 0;
  missing rules file → `[rules] MISSING`; output is valid JSON (`jq -e`).
- **Drift guard**: a test that greps the 5 oracle `CLAUDE.md` files and FAILS if any still contains a tier-1
  heading (`## Golden Rules`, `## Principles`, `Rule 6`) — this is what stops the copy-paste from creeping back.
- **Live**: one `maw wake` and one `/orches` dispatch; confirm the receipt line in the pane and that
  `skill_listing`-style accounting shows the expected byte delta.

## 7. Open decision — the contradicted rule

`Never merge PRs without human approval` is contradicted by the engine's **default**: `cmd_mode_get` ends
`echo online   # ⭐ default`, no `~/.config/mission-control/merge-mode` file exists, and `online` means
push `agents/<role>` → open PR → `gh pr merge --merge` automatically every sprint. Human approval is replaced
by code gates (verify-gate + `land` enforcing Traceability + PO decision).

**DECIDED 2026-08-14 (human): (a) reword the rule.** `cmd_mode_get` keeps `online` as its default; the engine
is not changed. Tier 1 will carry:

```
- Never merge without a passing verify-gate
- The merge mode (online/local) is set by the human; an agent must never change it
```

Rejected: (b) changing the default to `local` — it would keep the old wording but give up the per-sprint
GitHub audit trail.

Related: `Never commit secrets` is currently advisory — `cmd_sec_scan` is `rc 0` report-only and blocks `land`
only when `ORCHES_SEC_GATE=1`, which is set nowhere. Either set it or word the rule as advisory.

## 8. Cost

**Measured after phase A was built (2026-08-14) — the earlier "roughly flat" estimate was wrong.**

Actual file sizes: `universal.md` 3,497 B · `role-orchestrator.md` 1,938 B · `role-worker.md` 1,218 B
⇒ injected 4,715 B for a worker (~1,180 tok), 5,434 B for the orchestrator (~1,360 tok).

Phase B removes from each oracle's own file: foreman 1,841 B · bob 2,520 B · jack 1,971 B ·
john 2,234 B · mike 2,234 B (identity kept: 1,163 / 323 / 326 / 771 / 770 B).

Net per wake, measured after phase B landed: foreman 3,004 → 6,615 B (**+902 tok**) · bob 2,843 → 5,375
(**+633**) · jack 2,297 → 5,378 (**+770**) · john 3,005 → 5,823 (**+704**) · mike 3,004 → 5,822 (**+704**).
On disk across the fleet it is the other way round: 14,153 B in 5 files → 11,371 B in 5 identity files +
3 rule files = **−20%**, which is the dedup. So per-file smaller, per-session bigger. The increase is added
content, not bloat: the memory-layers block (~1 KB, new), the full 9-line Golden Rules (was 5, and absent
entirely for bob/jack), worker doctrine that existed nowhere outside the dispatch brief, and two
guardrails promoted out of auto-memory (`never maw wake a worker`, `delegate git ops in agents/<role>/`).

If that delta is unwanted, the cheapest trims are the memory-layers block (move to role-worker only) and
the Rule 6 signature examples. Non-oracle sessions are unaffected — the hook emits nothing.

## 9. Non-goals

- No change to `maw` source (read-only) and no change to `maw.config.json` defaults.
- No move of the oracle repos into role subdirectories (would break hardcoded paths).
- No change to the `/orches` brief's per-run content.
- Tenant isolation stays OFF; this spec does not touch the Oracle DB.
