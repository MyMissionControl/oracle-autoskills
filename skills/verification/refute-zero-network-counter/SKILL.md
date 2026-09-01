---
name: refute-zero-network-counter
description: 'Use when a claim rests on a tool''s self-reported ''downloaded 0'' / cache-hit / offline counter: prove real network I/O with an idle baseline, a counting localhost proxy, and dead-endpoint + offline…'
installer: auto-skill
created_at: 2026-09-01T17:36:19+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'verifier-subagent'
category: 'verification'
content_hash: 920be2526fbf9bb92131bf36938384e3d63331e271bd29474c43c5a0a8ae7a49
---
# Refute a tool's own "0 downloaded / offline / cached" counter

Use when a claim rests on a tool's self-reported counter ("downloaded 0", "cache hit",
"no network", "reused N") and you must prove whether real network I/O happened.
Vendor counters usually count only ONE artifact class (e.g. package tarballs) and stay
at 0 while the same command pulls tens of MB of metadata.

## Procedure

1. **Prove the box is online first.** `curl -s -o /dev/null -w '%{http_code}\n' <endpoint>`.
   If it is offline, "downloaded 0" is vacuous and the whole timing is an offline number.

2. **Idle baseline, twice.** Never compare against zero.
   ```
   nb() { awk '/eth0/ {print $2" "$10}' /proc/net/dev; }
   A=$(nb); python3 -c "import time; time.sleep(10)"; B=$(nb)   # foreground sleep may be blocked
   ```
   Record rx/tx delta for two separate idle windows. Typical: tens of KB per 10 s.

3. **Measure the command the same way.** Run it ≥2 times in fresh copies. If the deltas
   agree to <1% across runs, the traffic is deterministic protocol traffic, not noise —
   that reproducibility IS the attribution argument.

4. **Attribute to the process, not the box: counting localhost proxy.** Point the tool's
   endpoint config at a local forwarder that tallies bytes and request count, and have it
   dump the tally on SIGTERM. This yields "N requests, M bytes, all from this process" —
   unassailable, and it names the hosts being hit.

5. **Dead-endpoint control.** Re-run with the endpoint pointed at a closed port
   (`http://127.0.0.1:1/`). If the command fails and produces no artifact, network access
   is load-bearing, not opportunistic. Note the retry wall-time — it is the real worst case.

6. **Offline control.** Force the tool's offline mode (config/env, not always a CLI flag —
   `<tool> import --offline` may be "Unknown option" while `npm_config_offline=true` works).
   Then diff the artifact: if it is **byte-identical** (md5) but faster, the network round
   trip bought nothing and its seconds are pure, removable overhead.

## Reporting rules

- Split the claim: "0 tarballs downloaded" can be TRUE while "zero network" is FALSE.
- Give the delta next to the idle baseline, never alone.
- Re-time on ≥2 fresh copies before quoting any wall-clock total; a single draw on a
  burstable/shared VM can be off ±30%. Quote the observed range, not one number.
- Re-run on a second, larger input before letting the number generalise; cost usually
  scales with dependency/record count, so one project's total is not "the cost".
- Check the caller: read the code path and confirm the tool actually runs the command
  sequence that was benchmarked. A benchmark of `A && B` is wrong if the seam runs only `A`.
  Also read the seam's timeout — that, not the happy path, is the worst case.
