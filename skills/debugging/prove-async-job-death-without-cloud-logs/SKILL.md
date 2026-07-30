---
name: prove-async-job-death-without-cloud-logs
description: Use when a deployed app's background job is stuck in an in-progress state and you cannot read platform logs — prove slow vs hung vs dead from the public API and the code's own timeouts.
installer: auto-skill
created_at: 2026-07-28T03:50:05+00:00
created_session: 
trigger: complex-task
created_by: claude-opus-5
category: debugging
content_hash: 52aaecc435508727ceef10d549ad08892c097951481fcb7cafc14c81effdf661
---
---
name: prove-async-job-death-without-cloud-logs
description: Use when a deployed app's background job is stuck in an in-progress state (queued/processing/running) and you cannot read the platform's logs or metrics. Proves whether the job is slow or dead, and whether the worker process died, using only the public API plus the code's own timeouts.
---

# Prove a stuck background job is dead (no log access)

When a row/task sits at `processing` "forever", the tempting move is to blame slowness and raise a timeout. Establish which of three worlds you are in FIRST — slow, hung, or dead — because each has a different fix. This works when cloud RBAC/log access is denied.

## 1. Read the state through the public API, not the DB

Hit the app's own read endpoint for each stuck item and record `status` + `error` verbatim. Note which sibling items DID finish — a finished sibling proves the pipeline itself works and moves the question to concurrency/lifecycle.

## 2. Find every timeout on the job's own code path

Grep the worker for `timeout`, `timeout_seconds`, `SIGKILL`, `--max-time`. For each, trace what status the timeout path WRITES.

The key inference: **if a timeout exists that would mark the item `failed` after N seconds, and the item has been stuck far longer than N while still not `failed`, the job did not merely run long — the code that would have written `failed` never executed.** That means the thread/process is gone (restart, OOM kill, deploy) or blocked BEFORE the timeout-guarded call.

Also check whether the timeout is env-overridable — a huge value set in prod invalidates the inference. Confirm the deployed value, not the default in source.

## 3. Ask "is the CPU busy right now?" with latency

You usually cannot run `top` on the box. Measure instead:

```bash
for i in 1 2 3 4 5; do curl -s -m 30 -o /dev/null -w "%{time_total}s " $API/health; done
for i in 1 2 3; do curl -s -m 30 -o /dev/null -w "%{time_total}s " $API/<endpoint-that-hits-the-db>; done
```

Pick one endpoint that touches the datastore so you exercise more than a static handler. On a small single-core instance, an in-flight encode/heavy job shows up as hundreds of ms to seconds. Tens of ms means nothing heavy is running — the work is not merely slow.

Fast responses on a FIRST request also tell you the container is warm (it was not idle-shut-down), which distinguishes "platform recycled it and it is back" from "still down".

## 4. Name the architectural fault, not the trigger

Stuck-forever is rarely the encoder or the click. It is: **job state lives only in the process AND no code reconciles a non-terminal state after a restart.** Check for the reaper before proposing anything:

```bash
grep -rn "processing\|pending" --include=*.py --include=*.ts <app> | grep -iE "stale|orphan|reconcile|reaper|requeue|startup"
```

No hits = the fix is a startup reconciliation pass, not a bigger timeout. Also check whether the UI's recovery affordance is gated on the terminal state only (e.g. Retry shown only when `failed`) — if so, a stuck non-terminal row is unrecoverable by the user, which is the actual reported pain.

## 5. Verify the fix against the real binary, not stubs

Unit tests almost always stub the heavy subprocess. Run the app for real (local sqlite + local storage + the real encoder), then:

- fire N jobs at once and poll each status every second, tracking the PEAK count in the running state (must be your intended concurrency)
- `kill` the process mid-job, start it again, and assert the row self-heals to the terminal state with a message
- assert the reconciliation did NOT touch already-finished rows
- fire the duplicate action while one job runs and assert the refusal code (e.g. 409)

## If metric access does come back, one query settles it

Pull the memory/CPU metric at **PT1M** grain across the incident window, not PT1H — an hourly bucket hides the shape. Two signatures to read:

- a **gap with no datapoints at all** = the instance stopped reporting = it died. That is stronger evidence than any log line, because a killed container often never gets to log its own stop.
- the minutes just before the gap give you the actual resource that ran out.

Compare against the same metric on an idle hour to get the baseline, then quote the multiple (e.g. 88 MiB idle -> 887 MiB, on a box with 1.75 GB).

Re-check the permission itself before concluding it is missing: `az role assignment list --assignee <upn> --all` omits group-inherited grants. Use `--scope <resource-group-id> --include-groups --include-inherited`.

## Pitfalls

- A subprocess encoder/compressor with its thread count unset sizes per-thread buffers from the CPU count it *sees* — inside a container that is usually the HOST's core count, not the quota you pay for. So `-threads 1` (or the equivalent) is a MEMORY fix as much as a CPU one, and N concurrent copies multiply it. Check the input size before blaming "the file is held in RAM": if the inputs are megabytes and the spike is hundreds of megabytes, the encoder is the consumer, not the payload.

- A pooled-DB-connection theory (stale connection at job end) is a real alternative cause of "never leaves processing" — rule it in/out by checking for `pool_pre_ping`/`pool_recycle` before blaming the process.
- An in-process job registry is only authoritative if the app runs ONE worker process. Confirm the startup command (`--workers`, gunicorn config) before letting a reaper fail rows another process may own.
- Do not auto-requeue stale jobs at startup: if the job caused the crash, every boot repeats it. Fail with an explanation and let a human retry.
