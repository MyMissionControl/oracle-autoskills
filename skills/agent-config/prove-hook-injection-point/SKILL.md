---
name: prove-hook-injection-point
description: 'Use before wiring hooks into an agent launcher''s config: prove they fire, merge vs replace global hooks, and that a blocking hook blocks — one headless run on an isolated tmux socket.'
installer: auto-skill
created_at: 2026-08-05T08:17:06+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude'
category: 'agent-config'
content_hash: 7d4147c70273d05bda421308347e4ed655b1c7e791d644793507ecf3910a1659
---
# Prove an agent hook injection point before wiring it into a launcher

Use before adding hooks to a launcher's per-session config (`--settings`, a generated
settings file, skill frontmatter). Three things must be proven first, and all three
are cheap. Guessing any of them ships a silent no-op or kills an existing hook.

## What to prove

1. **Do injected hooks fire at all** at this injection point, on this version?
2. **Does the injection MERGE with or REPLACE the user's global hooks?**
   Replace = your change silently kills whatever global hooks the system already
   depends on. This is the one people skip and the one that breaks production.
3. **Does a blocking hook actually block** (if you plan to gate on `Stop`/`PreToolUse`)?

## Procedure

Run one throwaway headless session on an isolated multiplexer socket so a live
session is never touched.

```sh
P=/tmp/probe; mkdir -p "$P"; cd "$P"

# hook 1 — plain marker, proves "fires at all"
printf '#!/bin/sh\necho fired >> "$(dirname "$0")/markers.txt"; exit 0\n' > a.sh

# hook 2 — blocking hook that blocks EXACTLY ONCE via a counter file.
# Without the counter this loops forever and burns quota.
cat > b.sh <<'EOF'
#!/bin/sh
D="$(cd "$(dirname "$0")" && pwd)"
n=$(cat "$D/n" 2>/dev/null || echo 0); n=$((n+1)); echo "$n" > "$D/n"
echo "block-hook:$n" >> "$D/markers.txt"
[ "$n" = 1 ] && printf '{"decision":"block","reason":"probe"}\n'
exit 0
EOF
chmod +x a.sh b.sh
```

Write the settings JSON pointing at both scripts, then launch headless inside an
isolated socket, and **capture a side effect of a known GLOBAL hook in the same run**:

```sh
tmux -L probesock new-session -d -c "$P" \
  "<agent-cli> -p 'Reply with exactly: OK' --settings '$P/s.json' > out.txt 2>&1; \
   <read the global hook's observable side effect> > side.txt; touch DONE"
```

Wait for `DONE` (poll in a background command; do not foreground-sleep), then read:

- `markers.txt` has the plain marker -> **Q1 PASS**
- `markers.txt` has the block hook **twice** -> **Q3 PASS** (blocked once, agent
  came back and stopped again). Only once = the block decision was ignored.
- `side.txt` non-empty -> **Q2 = MERGE** (global hook still ran). Empty -> REPLACE,
  and injecting here is unsafe.

Kill the socket when done: `tmux -L probesock kill-server`.

## Picking the global-hook side effect for Q2

You need something a global hook writes that you can read from outside. Good ones:
a multiplexer pane/session option, a file the hook touches, a log line. If the only
global hook no-ops outside the multiplexer, run the probe **inside** the multiplexer
so it has somewhere to write.

## Rules

- Record the agent-CLI version with the result. This is a version-dependent fact;
  re-run after upgrades rather than trusting an old PASS.
- Never prove this by editing the real global config. The point is to avoid
  touching it.
- A blocking hook probe without the once-only counter is a quota bomb. Always
  gate it on a counter file.
- Anchor JSON field checks on the VALUE, not a wide glob: `*active*true*` matches
  `{"active": false, "other": true}`.
- Check the launcher's quoting before shipping: if the settings JSON is embedded
  in a shell string sent through `send-keys`/`eval`, a quote character inside a
  hook command breaks the launch. Prefer `--settings <file>` over an inline string.
