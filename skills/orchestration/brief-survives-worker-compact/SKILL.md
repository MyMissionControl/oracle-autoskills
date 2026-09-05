---
name: brief-survives-worker-compact
description: 'Use when an orchestrator dispatches a brief to a worker agent that may auto-compact mid-task: save the brief to a gitignored file in the worktree, and diagnose an idle-pane timeout from disk before…'
installer: auto-skill
created_at: 2026-09-05T23:03:02+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'jack'
category: 'orchestration'
content_hash: 56eb0aae960da1335a62b1f97fe2d29baf79def86e1d9ac86d968eb562258496
---
Use when an orchestrator dispatches a long brief into a worker agent's pane/session and the worker
may hit auto-compact mid-task. The brief lives ONLY in the worker's context: after a compact it is
gone, the worker cannot re-read it, and it will sit idle waiting for the orchestrator to answer —
which reads as a hang, not a question. Measured cost in one real sprint: a worker finished its code,
lost the brief, blocked on one missing command, and idled until the orchestrator's poll timed out.

## Prevent it at dispatch time (cheap, do it every dispatch)

1. Pick a filename the repo already ignores, so the extra file cannot dirty the worktree and fail a
   "clean worktree" merge gate. Check first:
   `grep -nE '^\.?<marker>' <worktree>/.gitignore` — reuse an ignored pattern (e.g. `.<tool>-brief.*`).
   ⛔ A pattern being listed in `.gitignore` does NOT mean the tool writes that file — verify with
   `ls <worktree>/.<marker>*` before telling a worker to read it (it may not exist at all).
2. Write the SAME text you dispatched into `<worktree>/<ignored-brief-file>` right after the dispatch
   call returns (the worktree exists only after dispatch creates it).
3. Confirm it did not dirty the tree:
   `git -C <worktree> status --porcelain | grep -v '^?? \.<marker>'` → must be empty.
4. End the brief with one line telling the worker: "this brief is saved at `<ignored-brief-file>` in
   your worktree root — if your context is compacted, `cat` it instead of waiting for me."

## Diagnose it when it already happened

A poll/timeout verdict plus an idle pane is ambiguous — it can mean working, dead, or blocked.
Read disk before concluding anything:

- `git -C <worktree> log --oneline <base>..<branch>` — commits exist → real work happened.
- `cat <worktree>/<progress-file>` — a worker following a write-as-you-go rule states plainly what it
  is blocked on and what remains. This is the fastest signal; read it before reading the pane.
- `ls <worktree>/<done-marker>` — absent → not finished, so the timeout is not a false alarm.
- Check the orchestrator's own inbox/message channel too. If it shows zero unread while the worker
  claims it asked a question, the channel did not deliver — do not wait for a message that will not
  come, and do not assume the worker is stuck on something unknowable.

Then answer the blocking question directly into the pane and re-poll. Prefer the multi-line-capable
send verb: a single-line-only verb rejects a multi-line message and the worker is never told anything
(the orchestrator sees a STOP, the worker sees silence). Verify the send reported success.

## Gotcha that eats a whole tool call

A host hook may scan the TEXT of your command and block the entire call when your brief quotes a
dangerous command — even when the brief is warning the worker against it. Nothing gets dispatched.
Rephrase the warning descriptively ("do not kill by matching the command line") instead of quoting
the literal command. ⛔ Never edit hook/permission config to get the message through.

## Verify

- After the preventive write: the brief file exists, `status --porcelain` is clean of anything but
  ignored markers, and the worker's next message does not ask for information the brief already had.
- After a diagnosis: the worker resumes and reaches its done-marker without a second stall on the
  same question. A repeat stall on the same question means the answer never landed — re-check the
  send verb's result, not the worker.
