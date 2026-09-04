---
name: kill-scope-silent-stop
description: 'Use when a stop/kill button silently does nothing: diagnose process-group ownership (pgid vs pid) before blaming the guard, and make refusals speak.'
installer: auto-skill
created_at: 2026-09-04T16:08:18+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude-opus-5'
category: 'process-management'
content_hash: ce14798c62843e6416560173d8645ca414b288afb20a8d59b1539ce5d7e1a776
---
# Diagnose a stop/kill button that silently does nothing

Use when a UI (panel, dashboard, CLI) offers "stop this process" and pressing it
produces **no effect and no message**, with nothing in any log. Assume the guard is
right and the *scope* is wrong before you weaken anything.

## Why this happens

Most process managers kill by **process group** (`kill -TERM -<pgid>`) so children die
too, and refuse when the group leader is a protected process (shell / editor / init).
But a child spawned **without `detached: true`** inherits its parent's process group.
So a helper the app itself spawned sits in the *app's own* group, and a group kill would
mean "kill the app". The guard refuses — correctly — and usually just `return`s.

The same trap hits a helper the user started from a terminal: leader is `bash`.

## Steps

1. Find the real pid behind the port/resource:
   `ss -ltnp | grep :<port>`   (or `lsof -i :<port>`)
2. Read its group and the group leader — this is the whole diagnosis:
   `ps -o pid=,pgid=,comm=,args= -p <pid>`
   `PG=$(ps -o pgid= -p <pid> | tr -d ' '); ps -o pid=,comm=,args= -p $PG`
   If the leader is the host app / a shell, the group kill was never going to be allowed.
3. Check for children before choosing pid scope:
   `ps -o pid=,args= --ppid <pid>`
   No children ⇒ killing the single pid is complete. Children ⇒ decide deliberately
   whether they should die (often they should NOT: a shared daemon).
4. Fix the **scope**, not the guard. Group-kill only when the group *is* the service
   (`pgid === pid`); otherwise signal the pid. The pid is safe to signal only when
   something already vouched for that exact pid — an args-signature match, a registry
   entry — not the leader's identity. Also refuse `pid <= 1` and `pid === process.pid`.
5. Fix the **silence** too: return an outcome
   (`stopped | not-running | refused | survived`) and surface anything that is not
   `stopped`. A guard that refuses without saying so is half the bug the user reported.
6. Verify by running the exact command the fixed code would emit, then re-scan:
   the resource is free, the pid is gone, and any sibling daemon is still up.

## Also check: bulk "stop all" enumerates from every source the UI lists

If the UI draws its rows from two scanners (e.g. project servers + app-managed
services), a "stop all" written against one of them walks an empty list and returns
silently. Prove it: run the old and new implementations against a fake target that only
the second scanner can see, and show the resource still held before / freed after.

## Traps

- `kill -SIG <pid>` vs `kill -SIG -<pgid>`: the leading dash is the entire difference.
  Give the builder a `{scope, id}` argument so the call site cannot get it wrong.
- Do NOT "fix" this by adding `detached: true` reflexively — that changes process
  lifetime (the helper now outlives the app) and does nothing for already-running ones.
  The spawn may be non-detached on purpose; check for a comment saying so.
- `pkill -f "<pattern>"` matches your own shell's command line and kills your session.
  Use `pgrep` first, then kill explicit pids.
- Confirm which sibling processes must survive (a proxy/daemon on another port) and
  assert they are still listening after the stop.
