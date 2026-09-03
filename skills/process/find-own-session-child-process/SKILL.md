---
name: find-own-session-child-process
description: 'Use when you must identify or restart the MCP/sidecar child process belonging to the current agent session among several identical ones. Safe pid identification, respawn, and verification.'
installer: auto-skill
created_at: 2026-09-03T13:40:54+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude-code'
category: 'process'
content_hash: 748145de2781ee873b6d7e00f288863b762b3d3ebca86a648b5ea02ec96a682d
---
# Find (and safely restart) the child process belonging to THIS agent session

Use when a long-lived child of your own session — an MCP server, a language server, a
sidecar daemon — is stuck and you must identify *your* instance among several identical
ones, then kill only that one. Getting this wrong kills someone else's process.

## 1. List candidates — do NOT use `ps` if a token-proxy rewrites it

A proxy/wrapper on the shell (e.g. rtk) can silently filter `ps` output and drop exactly
the long-lived processes you are hunting. Measured once: 31 lines returned out of 328 real
pids, with every MCP server missing and no error shown.

```bash
pgrep -af "<distinctive substring of the command line>"   # pgrep is usually not rewritten
# fallback if you must:  <proxy> proxy ps aux
```

Sanity-check the tool itself before trusting it:
`ps aux | wc -l` vs `ls /proc | grep -c '^[0-9]'` — these should be within one or two.

## 2. Identify YOUR instance by inherited environment, not by process tree

Process-tree and stdio-pipe matching both FAIL when the child is re-parented (systemd-run
--scope, setsid, double-fork). The reliable signal is the session id the harness exports
into every child's environment.

```python
import subprocess
SESSION = "<your session id>"          # from the harness/transcript path
PAT     = "<command line substring>"
pids = [int(x) for x in subprocess.run(["pgrep","-f",PAT],
        capture_output=True, text=True).stdout.split()]
def env(p):
    return dict(l.split("=",1) for l in open(f"/proc/{p}/environ").read().split("\0") if "=" in l)
def cmd(p):
    return open(f"/proc/{p}/cmdline","rb").read().replace(b"\0",b" ").decode()
mine = [p for p in pids
        if env(p).get("<SESSION_ID_ENV_VAR>") == SESSION      # e.g. CLAUDE_CODE_SESSION_ID
        and cmd(p).startswith("<expected interpreter/binary prefix>")]
```

Do not read `cmdline` truncated. Slicing it (`[:120]`) can cut mid-path and silently match
nothing — a "no such process" that is really your own bug.

## 3. Refuse to act unless exactly one candidate survives

```python
if len(mine) != 1: raise SystemExit("not killing: expected exactly 1 candidate")
```

Require several independent conditions (session-id env AND binary prefix AND *not* the
harness's own process). A single condition is how you kill the wrong thing.

## 4. Detect "newly spawned" with a set difference, never with shell grep

```python
before = set(pids_now())
proc = subprocess.Popen([...])          # or trigger the respawn
new   = pids_now() - before             # <- the only correct way
```

Shell filters like `grep -v -F -w -e "$LIST"` silently mis-parse a space-separated pid list
and hand back an OLD pid. Following that with `kill` destroys an unrelated process.
Clean up only pids in `new`.

## 5. Restart, then verify the new instance carries what you changed

Many harnesses respawn a killed stdio child automatically on the next tool call — try one
call before assuming a full session restart is needed.

```bash
tr '\0' '\n' < /proc/<newpid>/environ | grep <VAR_YOU_ADDED>
```

Verify at the process, not at the config file: a config edit does nothing for an already
running process that caches its state, and a wrapper edit does nothing until a respawn.

## Blast radius

Killing a sibling session's child is recoverable (that session's tool errors until it
reconnects) but it IS a visible failure for someone else. Say so plainly if it happens.
