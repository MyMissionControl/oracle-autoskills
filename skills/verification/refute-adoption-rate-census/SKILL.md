---
name: refute-adoption-rate-census
description: 'Use when a census claims N artifacts lack a tool''s feature so the tool/criterion is broken: reproduce the count, then classify each non-adopter against the tool''s shipped skip guards, deliberate…'
installer: auto-skill
created_at: 2026-09-01T19:14:50+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'verifier-subagent'
category: 'verification'
content_hash: 12d994ccb4427b6948bcbadeadff1524d75c1b0a4a5b3f253275c087566dce4a
---
# Refute an adoption-rate census before believing it

Use when a claim says "N of M artifacts lack <feature X> ⇒ the tool that applies X is broken /
criterion 'every project uses it' is FALSE". Raw counts are usually reproducible and usually
irrelevant — the conclusion dies on classification, not arithmetic.

## 1. Reproduce the count first (cheap, and it buys credibility)
Re-run their walk yourself. If the numbers match exactly, say so — then attack the inference.

## 2. Read the tool's own precondition guards, not just its happy path
Find the apply function (`_<tool>_adopt`, `ensure_*`, `migrate_*`) and list every `return 0`
before the work happens. Typical designed-skip reasons:
  - an opt-out marker file / env switch (`.<tool>-no-<feat>` walked up to the repo root)
  - a rival lockfile / competing toolchain already present
  - a shape the tool provably cannot handle (workspaces, monorepo, non-standard layout)
  - a missing input the conversion needs (no lockfile to import ⇒ nothing to convert)
Source comments often NAME the real-world projects deliberately excluded. Grep for the
project names from the "failure" list inside the tool's source — a hit inverts the finding.

## 3. Prove each skip empirically without mutating a read-only corpus
Do NOT run the tool on the real project. Copy ONLY the manifest/lockfiles into scratch,
`git init` (guards often walk up to `.git`), then run the tool's verb on the copy:

    mk(){ d=$W/$1; mkdir -p "$d"; git -C "$d" init -q -b main
          for f in "${@:2}"; do cp "$SRC/$1/$f" "$d/" 2>/dev/null; done; }
    mk <proj> package.json package-lock.json bun.lockb
    bash "$TOOL" <adopt-verb> "$W/<proj>"

Manifest-only copies reproduce the guard decision at ~0 cost even when the real tree is GBs.

## 4. Check for a DELIBERATE revert before calling non-adoption a failure
A missing feature can mean "applied, then removed on purpose". Look for:
  - a role/branch/worker named `drop-*`, `revert-*`, `no-*` in the run ledger
  - `git log --oneline` at the project root; read the commit that deletes the artifact
A verified+landed revert is positive evidence the tool FIRES — the opposite of the claim.

## 5. Clean the denominator
Walk output routinely contains non-projects that inflate "without":
  - git worktrees under `agents/*` (`.git` is a FILE containing `gitdir:`) = same repo again
  - build/cache artifacts the skip list missed (`.vite/deps/package.json` is `{"type":"module"}`,
    `.orches-stale-*`, `.turbo`, `.parcel-cache`)
Report distinct top-level projects, not raw manifest count.

## 6. Confirm the proxy actually tracks the real thing
A declared field is a proxy for real use. Verify with the physical effect, e.g. for a shared
content-addressed store count hardlinks, never `du`:
    st.st_nlink > 1 ratio over node_modules   # adopted ~90-99%, not-adopted ~0%
⛔ separate `du` invocations double-count hardlinked trees — never size two trees that share a store.

## 7. Run the tool's own shipped test for that seam
`tests/<feature>-*.sh` usually asserts the exact guards. Point TMPDIR at your scratch dir.
All-green there means the mechanism works and the census is measuring policy, not breakage.

## Verdict shape
Separate "the counts are right" from "the conclusion follows". State, per named counterexample,
which of: designed-skip / no-input / deliberate-revert / genuine-miss. Only the last is a defect.
