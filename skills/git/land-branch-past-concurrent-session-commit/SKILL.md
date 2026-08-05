---
name: land-branch-past-concurrent-session-commit
description: 'Use when ff-merge of your branch is blocked because another live session is editing the same working tree — recover by rebasing onto their commit, never git-apply into their tree.'
installer: auto-skill
created_at: 2026-08-05T14:04:53+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'main-chat'
category: 'git'
content_hash: ce7d3cc9f1c096788d125008dee56650aec99125d37a64390de2567118c753bf
---
When ff-merging your feature branch into a shared repo fails with "local changes would be overwritten" AND another agent/session is live-editing the same working tree, do NOT `git apply` your patch into their tree (you entangle with their in-flight edits — their next save/commit clobbers or mis-attributes yours, and the 3-way pollutes the index). Instead:

1. STOP. Don't force, don't stash their WIP, don't `git checkout` over it.
2. Check whether they've committed since you branched: `git reflog -5` — if HEAD moved past your branch-base to a new commit G, their WIP is now SAFE (committed as G), and the collision is resolved.
3. If their work is still uncommitted: wait for them to commit (or ask the user to have that session commit) — that is the only clean unblock.
4. Once HEAD is at their commit G: rebase your branch onto it — `cd <your-worktree>; git rebase G`. Distinct-region edits auto-merge; resolve small overlaps (e.g. a shared guard constant/ceiling) by recomputing the true value from the merged file, keeping both sides' comments.
5. Re-run the affected tests on the MERGED code (their changes + yours), then `git merge --ff-only <branch>` into the now-clean main + push.

If you already applied into their tree by mistake: reverse only your hunks (`git diff <base> <yourcommit> -- <files> | git apply -R`), delete your new files, strip any conflict markers keeping THEIR side, then `git reset` (mixed, never --hard) to clear the polluted index — verify their committed work is intact via reflog before concluding anything was lost.
