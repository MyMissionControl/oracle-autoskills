---
name: audit-git-action-buttons-via-state-replay
description: 'Use when a UI''s git action buttons (Pull/Push/diverged chips) show wrong state, a dead button, or a reported conflict: replay a throwaway repo through every state against the button logic.'
installer: auto-skill
created_at: 2026-08-10T14:45:37+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude-opus-5'
category: 'git'
content_hash: 20647344548f285ba9d3ac133a56abc3fe59fd0d51df64983d15ae803c0e17c7
---
# Audit a UI's git action buttons by state replay

Use when a UI (extension panel, dashboard, web app) shows per-repo git action
buttons — Pull / Push / Commit / "up to date" chips — and someone reports a
conflict, a dead button, or a wrong label. The bug is almost never in the git
command the button runs; it is in the **state that decided which button to
show**. Reading the code alone will not tell you which — you have to drive a
real repo through every state.

## 1. Find the two halves

Nearly every such UI splits into:

- a **pure decision function** (`raw git facts -> which button`), and
- a **runner** that executes the chosen git command.

Locate both. `grep` for the button kinds (`pull`, `push`, `diverged`,
`uptodate`) rather than for `git`, since the decision function never shells out.

## 2. Transcribe the decision function into bash

Re-implement the pure function as a shell function reading a real repo. Keep
the SAME precedence order as the source, comment-for-comment. This is the whole
trick: now you can ask "what button would the UI show?" about any repo state.

```bash
mcbutton() {                      # mirror of parseButtonState()
  local d=$1 porc up a b dirty
  porc=$(git -C "$d" status --porcelain -uall)
  dirty=$(printf '%s' "$porc" | grep -c '[^[:space:]]' || true)
  up=$(git -C "$d" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null)
  [ "$dirty" -gt 0 ] && { echo "commit($dirty)"; return; }
  [ -z "$up" ] && { echo push; return; }
  read -r b a <<<"$(git -C "$d" rev-list --left-right --count '@{u}...HEAD')"
  [ "$b" -gt 0 ] && [ "$a" -gt 0 ] && { echo "DIVERGED(${b}v ${a}^)"; return; }
  [ "$a" -gt 0 ] && { echo "push($a)"; return; }
  [ "$b" -gt 0 ] && { echo "pull($b)"; return; }
  echo uptodate
}
```

## 3. Build a throwaway origin + two clones

Bare repo, a "seed" clone that plays the OTHER developer, and the clone under
test. Pin `GIT_CONFIG_GLOBAL=/dev/null GIT_CONFIG_SYSTEM=/dev/null` and the
author env vars so the user's real config cannot change the result.

## 4. Drive it through EVERY state, printing button + real outcome

Minimum matrix — run each, print the button, then run the command the button
would run and capture full stderr and rc:

| state | what it proves |
|---|---|
| clean, strictly behind | the happy path actually fast-forwards |
| diverged (both moved) | the refusal is safe, tree untouched |
| dirty + behind, files OVERLAP | git refuses safely |
| dirty + behind, files DISJOINT | ff-pull SUCCEEDS — so "commit first" advice may be wrong |
| dirty + behind then commit | does the UI's own precedence CREATE the dead end? |
| remote tracks a locally-**ignored** file | silent clobber: `--porcelain -uall` hides ignored files, tree reads clean, pull overwrites at rc=0 |
| remote adds a file that exists untracked | git refuses |
| remote branch deleted | confusing message, wrong chip |
| detached HEAD | `@{u}` fails, so "no upstream" logic offers a push that can never work |
| stale: remote moved, no fetch yet | the chip lies; then push is rejected and the chip does NOT change |
| pre-existing `.git/index.lock` | does the write path self-heal? |

## 5. The two findings this always surfaces

**Staleness.** ahead/behind come from remote-tracking refs, i.e. from the last
fetch. If the UI only fetches on an explicit refresh, every chip is a claim
about the past. Check every render call site for whether it fetches; the
failure path (rejected push, refused pull) is the one that MUST refetch, or the
same doomed button stays on the row forever.

**The error toast names the wrong thing.** `stderr.split("\n")[0]` is the
standard implementation and it is almost always wrong: git prints its `hint:`
advice block, the `To <url>` push banner and the fetch summary BEFORE the real
reason. Capture real stderr from step 4 and build the picker from it —
`! [rejected]` > `fatal:` > `error:` > first non-noise line, folding in the
indented file list when the line ends in `:`, and a "timed out" fallback when
the process was killed with empty output.

## 6. Fix and prove

Turn the captured stderr into test fixtures verbatim (they are free, real, and
never go stale). Then replay the original symptoms through the fixed code and
print before/after — button before, toast old vs new, button after. That
before/after transcript is the deliverable, not the diff.

## Traps

- `--ff-only` cannot create a conflict. If conflicts are reported, look at the
  state feeding the button, not at the pull flag. `--ff` (without `-only`) can.
- `status --porcelain -uall` does NOT list ignored files. A repo can read
  perfectly clean while a pull is about to overwrite an ignored build artifact.
- Do not assert "the button is dead" from a missing handler alone — check
  whether the screen is reachable at all first (grep the entry point; dead code
  is a different, lower-priority finding).
- A search hook may rewrite grep/rg; if output looks truncated or mangled,
  re-run through the raw binary before believing a "0 matches".
