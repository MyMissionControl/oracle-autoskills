---
name: snap-cli-stdout-swallowed
description: 'Use when a snap-packaged CLI (/snap/bin/*, e.g. chromium --dump-dom) exits rc=0 but writes 0 bytes to a redirected file: the snap wrapper discards stdout to regular files, pipes survive.'
installer: auto-skill
created_at: 2026-08-11T08:40:41+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'probe-rootcause'
category: 'tooling'
content_hash: 5b48d2a9af2ca3ae71752bb06a66c487551c34fb9d6ff4d8888752163e8b4219
---
# Snap-packaged CLI writes 0 bytes to a redirected file

## Symptom
A snap-packaged CLI (`chromium`, or any `/snap/bin/<app>`) exits **rc=0** but the
redirect target is **empty**:

```bash
/snap/bin/<app> --some-flag > out.txt   # rc=0, out.txt = 0 bytes
```

You may wrongly conclude "the flag is broken / removed in this version".

## Root cause
`/snap/bin/<app>` is a symlink to `/usr/bin/snap` (i.e. `snap run <app>`).
The snap wrapper **discards the child's stdout when fd 1 is a regular file**.
When fd 1 is a **pipe**, the same output arrives intact.

## Diagnose in 3 commands
Use a flag that always prints, e.g. `--version`, as the control:

```bash
<app> --version > /tmp/a.out; wc -c < /tmp/a.out   # 0  -> stdout swallowed
<app> --version | cat                              # prints -> pipe survives
<app> --version 2>&1 > >(cat > /tmp/b.out)         # prints -> confirms fd-type is the variable
```

If the control flag ALSO yields 0 bytes to a file, the feature is fine — the
wrapper is the problem. Do **not** blame the feature.

## Fix — pick one
```bash
# 1) Pipe instead of redirect (simplest)
<app> <flags> | cat > out.txt
<app> <flags> | tee out.txt

# 2) Bypass the wrapper: exec the real binary inside the snap
find /snap/<app>/current -maxdepth 6 -name <realbin> -type f
/snap/<app>/current/usr/lib/<app>/<realbin> <flags> > out.txt   # file redirect WORKS here
```

## Second, independent snap trap: hidden dirs are denied
Snap's `home` interface grants **non-hidden** paths in `$HOME` only. Pointing a
snap app at a dotdir fails:

```bash
<app> --user-data-dir="$HOME/.cache/foo"   # rc=21, "Failed to create ... Permission denied"
```

Confirm it, don't guess:
```bash
journalctl -k --since "-15 min" | grep DENIED | grep -i cache
# apparmor="DENIED" operation="symlink" name=".../.cache/foo/SingletonLock"
```
Use a **non-hidden** dir (`$HOME/work/prof`) or omit the flag entirely.
Also: any OUTPUT path you hand a snap must be under `$HOME` and non-hidden.
Shell redirects are performed by bash, so those paths are unconstrained.

## Rule out the lookalikes before blaming a version regression
- Re-run through any command-rewriting hook's passthrough (e.g. `rtk proxy ...`)
  to prove the hook is not the cause.
- Compare against a **non-snap** build of the same app if one exists
  (`~/.cache/ms-playwright/*`, `/opt/<vendor>/`) — that cleanly separates
  "packaging" from "this version removed the feature".
- Cosmetic AppArmor denials (vulkan, dconf) are noise; match the denial's
  `name=` against the resource you actually care about.

## Hygiene
Bound the app with `timeout 60`. Kill background servers by resolving the
listening PID and verifying `/proc/<pid>/cmdline` first — never a bare
`pkill -f <pattern>`, which can match your own shell.
