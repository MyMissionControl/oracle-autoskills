---
name: toctou-atomic-create-fix-and-test
description: Use when a check-then-write (TOCTOU) file race lets concurrent processes clobber each other. Fix via atomic exclusive create (open x); prove it with a deterministic monkeypatch test, not flaky timing.
installer: auto-skill
created_at: 2026-07-20T07:06:15+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: concurrency
content_hash: 133672b1d2d4227dd21275488e2694b5b6b0fca4b734a7f512451bf743997cd4
---
# Close a check-then-write (TOCTOU) file race + prove the fix deterministically

Use when two processes can create/write the SAME file concurrently and the code
does `os.path.exists(dest)` then later `open(dest, "w")`. Both callers can pass
the existence check in the gap and clobber each other — the loser's data vanishes
with no error. (Classic case: parallel workers/agents each writing `<name>/FILE`.)

## Fix — atomic exclusive create (first-writer-wins)

Collapse check-then-write into ONE exclusive-create syscall; the OS picks a single
winner. Everyone else gets `FileExistsError` and reconciles the same way a
pre-existing file already did:

    os.makedirs(dest_dir, exist_ok=True)
    try:
        with open(dest, "x") as f:      # O_EXCL: only one process can create it
            f.write(payload)
        emit("created"); return
    except FileExistsError:
        pass                            # pre-existing OR lost the race -> reconcile below
    if same_content(dest):  emit("exists-identical"); return
    if not force:           emit("refused-conflict"); return   # different content -> refuse, NO clobber
    open(dest, "w").write(payload)      # explicit --force overwrite only

Every non-concurrent path behaves exactly as before; only the silent-clobber case
turns into a refusal. Cross-platform (works on Windows too), stdlib only.

Note: `emit()` here calls sys.exit via SystemExit, which is NOT caught by
`except FileExistsError` — so the created-path exits cleanly and never falls
through to the reconcile block.

## Prove it deterministically — do NOT rely on timing / flaky stress loops

Spawning N subprocesses rarely lands two callers inside the microsecond window,
so such a test false-greens on the buggy code. Force the ordering instead:
monkeypatch a syscall that runs INSIDE the window (e.g. the `os.makedirs` that
sits between the exists-check and the write) to drop a rival's DIFFERENT file
first, then assert the code REFUSES and leaves the rival intact.

    real = os.makedirs
    def racing(path, *a, **k):
        real(path, *a, **k)
        if os.path.basename(path.rstrip(os.sep)) == name and not os.path.exists(dest):
            with open(dest, "x") as rf:      # rival lands in the gap
                rf.write(rival_bytes)
    target_module.os.makedirs = racing
    try:
        ns.fn(ns)                            # run create in-process
    except SystemExit:
        pass                                 # emit() exits; swallow it
    finally:
        target_module.os.makedirs = real
    assert status == "refused-conflict" and rival_marker in open(dest).read()

Workflow: run the test on the OLD code FIRST — it MUST fail (status "created",
rival gone). Only then apply the fix and confirm green. Keep a real multi-process
stress test too as a positive integration guard, but know it can't reliably fail
on the buggy code, so it cannot replace the deterministic one.
