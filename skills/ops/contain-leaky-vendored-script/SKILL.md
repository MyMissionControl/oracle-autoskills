---
name: contain-leaky-vendored-script
description: Use when a vendored/read-only repo's script leaks memory until host OOM. Self-cap via in-script systemd-run re-exec, marker-test output, restore via read-only worktree of a good branch.
installer: auto-skill
created_at: 2026-07-18T14:46:17+00:00
created_session: 
trigger: error-recovery
created_by: soulbrew-main-chat
category: ops
content_hash: 1c0868a950afa6f0f0298d78dfdd01dfdf8002f1be9396a0b51126ed81861a16
---
# Contain + swap a leaking vendored script (read-only repo)

Use when a script imported from a vendored/third-party repo (<vendor-repo>, treat as read-only) leaks memory until it OOMs/freezes the host, and callers are scattered (hooks, systemd services, other sessions with CACHED command lines).

## 1. Contain — self-cap INSIDE the script (covers every caller)
Callers cache the COMMAND, but the script BODY is read fresh on every spawn. So put the cap in the script itself, before any heavy import:
```ts
const CAP_FLAG = 'SELF_CAPPED';
if (!process.env[CAP_FLAG]) {
  const probe = Bun.spawnSync(['systemd-run','--user','--scope','-q','true']);
  if (probe.exitCode === 0) {
    const child = Bun.spawnSync(
      ['systemd-run','--user','--scope','-q','-p','MemoryMax=3G','-p','MemorySwapMax=512M',
       process.execPath, import.meta.path],
      { env: { ...process.env, [CAP_FLAG]: '1' }, stdout: 'inherit', stderr: 'inherit' });
    process.exit(child.exitCode ?? 1);
  }
} // fallback: run uncapped rather than break the pipeline
const { heavyFn } = await import('<vendor-repo>/path/mod.ts'); // dynamic AFTER cap
```
- MemorySwapMax is REQUIRED when host swap exists — bare MemoryMax pages into swap and keeps growing (thrash) instead of being killed.
- Verify live: find child pid, read /sys/fs/cgroup$(cut -d: -f3 /proc/PID/cgroup)/memory.max.

## 2. Prove whether killed runs still did their job (marker test)
Write a marker input (e.g. a new file the pipeline should ingest), run once, then query the OUTPUT store for the marker. Killed-before-write = the pipeline is BROKEN, not just leaky — containment alone silently loses data. Also measure the true ceiling: run once under a high cap (e.g. 8G) sampling VmRSS; if even a zero-delta run exceeds it, no cap can make it complete.

## 3. Restore function — read-only worktree of a known-good branch
If a known-good branch/tag exists (pre-regression fork), swap the ENGINE without touching the repo:
```bash
git -C <vendor-repo> worktree add ~/.<name>-good <good-branch>   # no commits added; main checkout untouched
cd ~/.<name>-good && bun install --frozen-lockfile               # deps live in the worktree only
```
Repoint YOUR wrapper's import (and any service config) at the worktree path. Back up the data store first; rerun the marker test — expect success + tiny RSS. Note the revert path in a comment: repoint imports back + `git worktree remove` when upstream fixes.

## Pitfalls
- Test the WRITE and READ sides separately: it's fine to run old-branch write code against a newer store if inserts succeed (schema drift often additive) while the new code keeps serving reads — verify with the marker query through the normal read path.
- A watchdog that polls-and-kills uncapped processes is only a stopgap: it races the balloon (GB/s) and dies with the host; retire it once the self-cap lands.
- systemd-run --user needs the user manager (XDG_RUNTIME_DIR); always keep an uncapped fallback so the pipeline never hard-breaks in odd contexts.
