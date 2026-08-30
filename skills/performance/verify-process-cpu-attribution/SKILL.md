---
name: verify-process-cpu-attribution
description: 'Use when confirming or refuting a claim that a specific process is eating N% CPU: /proc deltas over a correctly-timed window, cutime/cstime for forked-child cost, sub-second sampling to tell…'
installer: auto-skill
created_at: 2026-08-30T15:59:00+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'adversarial-verifier-subagent'
category: 'performance'
content_hash: 2ea56992620e738299608a82b4a3a047114f845744b6e3888c7f3e82f4ae263c
---
# Verify a per-process CPU attribution claim

Use when someone claims "process X is eating N% of this box" and you must confirm or refute it
without killing anything. Four traps make most such claims wrong.

## 1. Never trust `ps %CPU` — it is a LIFETIME AVERAGE
`ps` computes cpu_total/elapsed since process start. A process that burned a core for 10 min an
hour ago still reports high. Re-measure with a /proc delta over a real window:

```
python3 - <<'EOF'
import os,time
def snap():
    d={}
    for p in os.listdir('/proc'):
        if not p.isdigit(): continue
        try:
            s=open('/proc/%s/stat'%p).read()
            r=s[s.rindex(')')+2:].split()          # rindex(')') survives comms with spaces/parens
            d[int(p)]=(int(r[11])+int(r[12]), s[s.index('(')+1:s.rindex(')')])
        except Exception: pass
    return d
a=snap(); t0=time.time(); time.sleep(4); b=snap(); w=time.time()-t0
rows=sorted(((b[k][0]-a[k][0],k,b[k][1]) for k in b if k in a and b[k][0]>a[k][0]),reverse=True)
tot=sum(r[0] for r in rows)
print("window=%.2fs  BOX TOTAL=%.2f cores"%(w,tot/w/100))
for d,pid,c in rows[:15]:
    print("%6d %-8d %-16s %.3f cores = %.1f%% of box"%(d,pid,c,d/w/100,d/w/(os.cpu_count())))
EOF
```

**Window-skew trap:** do NOT take `t1` before the second read loop, and do not spawn one `awk` per
pid — the loop itself takes seconds and you will compute impossible values (>100% of all cores).
Read all of /proc in one pass inside the timed region.

## 2. Sampling the PID alone MISSES fork cost — read cutime/cstime
A process that forks a helper per poll tick charges that CPU to its *children*. Per-process
sampling attributes ~0 to it. Fields 16/17 of /proc/<pid>/stat (cutime/cstime) accumulate REAPED
children's CPU:

```
read -r -a f < <(sed 's/.*) //' /proc/<pid>/stat)
echo "self=${f[11]}+${f[12]}  reaped_children=${f[13]}+${f[14]}"   # ticks; /100 = seconds
```
Delta cutime+cstime over a window = the live fork cost. It is routinely LARGER than the parent's
own CPU, so a parent-only measurement understates the true total. Always report self / children /
total separately.

## 3. Transient `<defunct>` is NOT a reap leak
Every forked child is briefly Z between exit and wait(). One `ps` frame showing zombies proves
nothing. Distinguish leak from normal churn by sampling sub-second:

```
python3 -c "
import os,time
for i in range(10):
    z=[(int(p),int(open('/proc/%s/stat'%p).read().split(') ')[1].split()[1]))
       for p in os.listdir('/proc') if p.isdigit()
       and open('/proc/%s/stat'%p).read().split(') ')[1].split()[0]=='Z']
    print(i,z); time.sleep(0.5)"
```
- Same pids persisting across samples, count climbing = real leak.
- Different pids each time, gone within 1 sample, count returns to zero = normal fork/wait churn.
Cross-check accumulation: a true leak also shows a growing child count in the parent's process
tree. Zero zombies in a full /proc walk refutes "they pile up".

## 4. Subtract the observer
On a box being investigated by several agents, the investigation is often the top consumer.
Before blaming anything, check whether top pids are your own or a sibling's tooling
(`journalctl`, `rg`, headless `chrome`, `find`). Trace ancestry:
```
p=<pid>; for i in $(seq 6); do [ -r /proc/$p/stat ] || break;
  echo "$p $(cat /proc/$p/comm): $(tr '\0' ' ' < /proc/$p/cmdline | cut -c1-100)";
  p=$(sed 's/.*) //' /proc/$p/stat | cut -d' ' -f2); done
```
Transient pids that vanish between two commands are almost always observer processes. Note the
box total, then rank suspects against it — a 5%-of-box process cannot explain a saturated box.

## Reporting rule
Give: (a) the window length, (b) self / children / total in CORES and as % of the box,
(c) the box total for scale, (d) which top consumers are observers. Mark unverified identity
attributions as speculation — holding a log file (e.g. an exthost.log) proves role; forking a
given helper does not.
