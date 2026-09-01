---
name: reverify-acceptance-after-closeout-mutation
description: 'Use when an acceptance/fresh-clone/smoke gate passed and a close-out or delivery tool then wrote to the repo — pin the gate''s commit, diff the shipped tree, revert tool side effects, and re-run the…'
installer: auto-skill
created_at: 2026-09-01T14:40:00+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'jack'
category: 'orchestration'
content_hash: cd78359367ec57d1b55a43fb13b577d92097a3e890a40a19b8a1c8252bb6fea9
---
# Re-verify acceptance on the final commit when close-out tooling mutates the repo

Use when a run-level acceptance gate (fresh-clone / bootstrap / smoke / deploy-probe) has PASSED, and afterwards you run any close-out or delivery tool that can **write to the repo** (dependency adoption, lockfile generation, config injection, doc/marker generation, auto-commit of `-A`). The PASS you hold is bound to a commit, not to the run — once the tree moves, it is stale.

## The failure this prevents

A delivery checker adopted a different package manager into the project: added a `packageManager` field, a tool-specific rc file, and a second lockfile. The orchestrator removed them. Then the *sprint-close* verb called the same checker again and committed everything with `git add -A`. Shipped state now declared package manager B while the README documented package manager A — so the documented install command could be rejected on any machine with the shim enabled. The acceptance gate still reported PASS, because it had run **before** those commits. Nothing in the pipeline noticed; it surfaced only because an unrelated verb happened to print the stray filename.

## Procedure

1. **Record the gate's commit.** Immediately after any acceptance gate passes:
   ```bash
   GATE_SHA="$(git -C "$PROJ" rev-parse HEAD)"; echo "gate passed at $GATE_SHA"
   ```
2. **Treat every close-out tool as a mutation, not a read.** Before and after each one:
   ```bash
   git -C "$PROJ" status --porcelain          # before: expect only your own known edits
   <close-out / delivery / record command>
   git -C "$PROJ" status --porcelain          # after: anything new here is the tool's, not yours
   ```
3. **Diff the shipped tree against the proven tree** before declaring done:
   ```bash
   git -C "$PROJ" diff --stat "$GATE_SHA"..HEAD
   git -C "$PROJ" diff --name-only "$GATE_SHA"..HEAD | grep -Ei 'lock|rc$|^\.[a-z]+rc|package\.json|Dockerfile|compose|\.env'
   ```
   Empty grep = the install/boot path is untouched, the PASS still holds. Any hit = the PASS is stale.
4. **Revert tool side effects through the normal work path, not by hand.** Under a no-self-edit rule, dispatch a scoped task limited to exactly those files. Have it (a) remove the injected field/files, (b) **add them to `.gitignore`** so the tool cannot silently re-add them, and (c) prove the documented install + boot commands still work from a clean tree.
5. **Re-run the gate on the real final commit.** Do not reuse the earlier result and do not reason that the diff "looks harmless":
   ```bash
   bash <acceptance-gate> "$PROJ"      # fresh clone / bootstrap / smoke — whichever proves the claim
   ```
6. **Correct the record.** If any generated report or table shows the older result, add a line stating which commit each gate result belongs to, and that the gate was re-run on the shipped commit.

## Rules

- A gate result is `(gate, commit)`. Quoting a PASS without its commit is how a proven-but-not-shipped state escapes.
- Metadata that contradicts the documented run instructions is an **acceptance-level defect**, not tidiness — the documented command genuinely fails for some users.
- A tool that "fixes things for you" during close-out is the highest-risk step in the run: it runs last, after every check, and its writes look like yours in `git status`.
- Never rely on incidental output to catch this. Step 3 is a required step, not a fallback.
