---
name: diagnose-cpu-pegged-inference-daemon
description: 'Use when a local model/inference daemon pegs CPU on a small box: prove burn-vs-starve from /proc deltas, catch thread-count-vs-cgroup-quota spin thrash, and find the per-request-timeout livelock…'
installer: auto-skill
created_at: 2026-08-30T16:17:16+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude-opus-5'
category: 'performance'
content_hash: 4e1477083422ec4987262d4045021c45481e6a06244f45d44bcaa7427fa5068d
---
# Diagnose a CPU-pegged local inference daemon

Use when a local model server (ollama/llama.cpp/vLLM/any batch worker) pegs the CPU on a
small box and the obvious answer ("too much work queued") does not explain it.

## 1. Prove it is BURNING, not STARVED

`ps %CPU` is a lifetime average and will lie. Measure wall time and consumed CPU in the
same window:

```bash
read a b < <(awk '{print $14, $15}' /proc/<PID>/stat); t0=$(date +%s.%N)
<one request>
t1=$(date +%s.%N); read c d < <(awk '{print $14, $15}' /proc/<PID>/stat)
awk -v a=$a -v b=$b -v c=$c -v d=$d -v t0=$t0 -v t1=$t1 \
  'BEGIN{cpu=(c+d-a-b)/100; w=t1-t0; printf "wall=%.2fs cpu=%.2fs -> %.0f%% of one core\n",w,cpu,cpu*100/w}'
```

- cpu ≈ wall x N cores  -> genuinely burning. Go to step 2.
- cpu << wall           -> starved / waiting. Different problem.

## 2. Thread count vs cgroup quota = spin thrash

The classic pathology on a capped service: the runtime sizes its thread pool from
`nproc`, but the cgroup quota only allows a fraction of that. Threads get frozen
mid-barrier by the quota while the rest spin-wait -> huge CPU for no work.

```bash
systemctl show <svc> -p CPUQuotaPerSecUSec -p CPUWeight -p Nice
cat /sys/fs/cgroup/system.slice/<svc>.service/cpu.stat   # nr_throttled / nr_periods
ps -o nlwp -p <PID>
```

`nr_throttled` a large fraction of `nr_periods` + threads >> quota-in-cores = confirmed.

**Prove it before changing config** by varying threads per request if the API allows
(e.g. ollama `"options":{"num_thread":N}`), warming first so model-load time is excluded:

```
num_thread=2  -> 2.6s      <- matches quota
num_thread=4  -> 20.6s
default(11)   -> 21.0s     <- 8x waste
```

Set threads ~= quota-in-cores. If there is no env var for it, bake the parameter into the
model/config **under the same name callers already use**, so no caller config changes:
`ollama create <same:tag> -f Modelfile` with `FROM <backup:tag>` + `PARAMETER num_thread N`.
Tag a backup first (`ollama cp <name> <name>:orig`) and verify the output dimension is
unchanged, or every stored vector is invalidated.

## 3. Per-request timeout smaller than one unit of work =永 livelock

Look for this shape in the client:

```js
if (errors === 0) saveState(progress)   // all-or-nothing
```

If one batch cannot finish inside the per-request timeout, EVERY batch aborts,
`errors > 0`, progress is never persisted, and the identical work is redone on every
schedule tick — forever. It looks like "the queue is always busy".

Detect without reading code: compare the progress/state file's mtime against the job's
last "completed" log line. **State mtime older than a successful completion = the job is
discarding its own work.**

```bash
stat -c '%y' <state-file>
journalctl --user -u <svc> --since '4 hours ago' | grep -i <done-marker> | tail
```

Then size one real unit of work against the timeout with actual production data, not a
toy string — a 25-char probe can be 100x faster than a real 1KB document.

Fix: batch small enough that one batch lands well inside the timeout, AND raise the
timeout. Do both; either alone leaves no margin.

## 4. Always add these two when you touch the supervisor

- **Wall-clock kill on the child.** A per-request timeout bounds one HTTP call, never the
  whole run. `await proc.exited` with no deadline lets a stuck pass run unbounded.
- **Stop discarding the child's output.** `stdout:'ignore', stderr:'ignore'` is why the
  failure was invisible for hours. Pipe it and log the last few lines.

## Gotchas

- `pkill -f "<script name>"` matches your own shell's command line and kills your session
  (exit 143/144). Filter on the interpreter path, or exclude `$$`.
- Redirecting a bun/node child's stdout to a FILE is block-buffered: kill it and the log
  is empty, which reads as "it hung at startup". Let it exit, or pipe it.
- Harness Bash timeouts cap well below long jobs (often 10 min). Run the proof pass with
  `run_in_background`, not a longer `timeout`.

## Done means

`errors=0` in the job's own output, the state file's mtime moved, and a recount of pending
work returns 0 — not just "load went down".
