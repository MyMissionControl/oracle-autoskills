---
name: config-twin-vs-auth-ban
description: 'Use when a daemon returns the same status for every key on a route family and a hardening flag is blamed: single-line config twins, key matrix with controls, consecutive-vs-interleaved ban probe…'
installer: auto-skill
created_at: 2026-09-03T10:11:23+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'm5-m4-adversarial-probe'
category: 'security'
content_hash: 228d83c95671547d6dd71994ca581102c1b8cd2ea3e21bff10395d6af69cf776
---
# Refute a config flag blamed for uniform auth failure

Use when a daemon/service returns the **same status for every key** on a whole route family
(e.g. "403 on all /management/* no matter what token") and a note blames a hardening flag
(`disable-control-panel: true`, `allow-remote: false`, a firewall setting). Uniform-across-keys
is the signature of a **rate-limit / IP ban / route-disabled** gate, not of a per-key auth flag —
a real auth flag gives you 200 for the right key.

## Procedure

1. **Never test on the live instance.** Copy its config to a scratch dir, change only the port,
   spawn the same binary on a high spare port, kill by exact pid later
   (`kill <pid>` after checking `/proc/<pid>/cmdline` contains your scratch path — never `pkill`).

2. **Build config twins that differ by ONE line.** For each suspect flag emit two configs identical
   except that line. Without this control a binding/auth observation proves nothing:

       sed -e 's/^port: A/port: B/' -e 's/^  <flag>: X/  <flag>: Y/' cfgA.yaml > cfgB.yaml

   Run both simultaneously and compare. Example result that settles a claim:
   config with no `host:` key binds `*:PORT`; the byte-identical config plus `host: "127.0.0.1"`
   binds `127.0.0.1:PORT` — so the missing key, not anything else, is the cause.

3. **Run the full key matrix WITH controls,** never just the happy path:
   no key / correct key / wrong key / a key valid for a *different* plane (data-plane key against
   the management plane). Distinct codes (401 vs 200 vs 403) mean auth is working per-key.

4. **Test for a ban before believing a flag.** Fire N *consecutive* bad auths, then retry the
   KNOWN-GOOD key after each:

       for i in $(seq 1 12); do bad=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer bad-$i" $URL)
         good=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $REAL" $URL)
         echo "$i bad=$bad good=$good"; done

   **Interleave a good call in a second run** — many implementations reset the failure counter on
   success, so an interleaved loop never bans and a consecutive loop does. Reporting only one of
   the two runs produces a false threshold. Read the ban body: it usually names the cooldown.

5. **Check whether the service rewrites its own secret on disk.** Daemons commonly bcrypt-hash a
   plaintext `secret-key` in place at load. Anything that later reads the secret *from that file*
   sends the hash, gets 401, and after a few tries trips the ban from step 4 — which then looks
   exactly like the flag everyone blamed. Grep the on-disk value's shape (`$2a$10$...`) before and
   after a start.

6. **Verify a static asset is not a data leak** before calling it one: fetch it unauthenticated and
   grep the body for a planted canary, and confirm every API route still returns 401 unauthenticated.
   Serving a UI bundle is attack surface, not disclosure.

## Reporting

Separate `MEASURED` from `READ`. A flag's effect is only MEASURED if a one-line twin proved it.
Say which of two compounding settings is load-bearing rather than listing both as blockers.

## Cleanup gate

`ss -ltnp | grep -E '<your port range>|<live port>'` must show only the live listener, and
`pgrep -a -x <binary>` only the production pid, before you report.
