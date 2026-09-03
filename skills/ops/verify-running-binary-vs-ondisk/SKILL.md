---
name: verify-running-binary-vs-ondisk
description: 'Use when a claim says a daemon runs binary X (md5/version-pin/handover audits): compare the executed image via /proc/PID/exe, not the path - stat without -L is the false-refutation trap.'
installer: auto-skill
created_at: 2026-09-03T14:55:56+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'adversary-subagent'
category: 'ops'
content_hash: 1183c4936c702f18bac720497bd3ebd40930438c20bd420761862265c6611de4
---
# Verify a running daemon executes the binary you think it does

Use when a claim asserts "the binary <supervisor> actually executes is X" (md5/version pin/
handover audits), or when a supervised daemon may have had its executable swapped underneath it.
On Linux `unlink()` of a running executable SUCCEEDS (no ETXTBSY), so the on-disk file at the
ExecStart path and the image the process is really running can diverge silently and forever.

## The trap that produces a FALSE refutation

`stat -c %i /proc/<pid>/exe` stats **the /proc symlink itself**, not the executed image, and returns
a procfs inode that never matches the real file. Two runs will look like a smoking gun:

    stat -c %i /proc/$P/exe        -> 246324   (procfs inode - MEANINGLESS)
    stat -c %i /path/to/binary     -> 421691

That is not evidence of a swap. `stat` dereferences ordinary symlinks by default but /proc/PID/exe
is a magic link; you must pass `-L` to resolve to the executed inode.

## Procedure

1. Resolve the supervisor's real pid and argv - never trust the unit file alone:

       P=$(systemctl --user show <unit> -p MainPID --value)
       systemctl --user show <unit> -p ExecStart -p ActiveState -p NRestarts -p ExecMainStartTimestamp
       tr '\0' ' ' < /proc/$P/cmdline; echo

2. Prove the pid is the one actually serving (a second, hand-spawned instance may hold the port):

       pgrep -af <binary-basename>          # NOT `ps` if a token-filter hook is installed
       ss -ltnp | grep <port>

3. Compare the EXECUTED IMAGE, not the path. This is the load-bearing step:

       md5sum /proc/$P/exe                  # bytes the kernel actually mapped
       md5sum /path/to/binary               # bytes on disk now
       stat -L -c 'dev=%d inode=%i size=%s mtime=%y' /proc/$P/exe /path/to/binary

   `ls -l /proc/$P/exe` showing ` (deleted)` is the swap tell, but a same-path replacement that
   preserved mtime will NOT show it - only the md5/inode comparison is decisive.

4. Verify the VERSION independently of the manager's own bookkeeping files. `.version` /
   `.version-pin` / a JSON manifest are claims written by the installer, not proof. Read the
   version out of the artifact without executing it:

       go version -m <binary>                                  # Go binaries, if go is installed
       strings -a <binary> | grep -aoE '<ver-regex>' | sort | uniq -c | sort -rn

   Exactly one version family appearing confirms it; two means the pin file may be lying.
   Do NOT run `<binary> --version` to check: an unrecognized flag can boot a real server and
   collide with the live daemon's port.

5. Separate the RECORD from the CONTROL. Find every call site of the checksum comparison:

       grep -n '<md5-var-name>' <engine-script>
       grep -c md5 <unit-file>

   If the check returns 0 unconditionally (report-only), or its only call site is a spawn path
   the live supervisor does not use, then a matching checksum is bookkeeping - it proves nothing
   about the future and did not gate the running process. Say so explicitly.

6. Enumerate the real flips, not just the blocked one. Read the guard/shim and check whether a
   sibling subcommand has the same effect and is unblocked (e.g. `--update` blocked but
   `--install <version>` not). A guard's own error text often recommends the unguarded twin.

## Reporting rule

"md5 of the ExecStart path" is a DISK fact. "the binary the supervisor executes" is a PROCESS fact.
A claim that cites the first to support the second is unsupported as written even when it happens
to be true - report the gap and the check that closed it.
