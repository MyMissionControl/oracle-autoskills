---
name: wire-local-daemon-hop
description: Use when routing an existing CLI/agent through a local proxy or sidecar daemon: prove the knob with a dead-port control, fail closed when a dead far end hangs, refcount the shared daemon.
installer: auto-skill
created_at: 2026-08-26T15:35:41+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'chillox-intern'
category: 'integration'
content_hash: 9d2468234aa25d1428cee3f0b7664af388e3150152d58c858fda380b2d736f8e
---
# Wire a client through a local daemon hop

Use when you route an existing CLI/agent through a local proxy or sidecar it did not
ship with — a translating gateway, a token-refreshing hop, a recording proxy. The
client keeps working, so the failure modes are all silent. Three things decide whether
the wiring is safe, and only one of them is "does it work".

## 1. Prove the knob with BOTH controls — the negative one settles it

A positive result ("the request arrived, the answer came back") is compatible with the
client having ignored your config and reached its original endpoint anyway. Point the
setting at a **dead port** and run the same call:

    # positive: config-file only, the env deliberately stripped
    env -u <VAR1> -u <VAR2> <client> --config <file> -p 'reply with exactly: PROVED'
    # negative: same file, far end at a closed port (127.0.0.1:9)

Then classify what the negative did — this is the input to every later decision:

| Negative result | What it means |
|---|---|
| Clear error, non-zero exit | You can let gates warn and continue |
| **Hangs until timeout** | Every gate must fail CLOSED (see §2) |
| Answers anyway | The knob is NOT honored; stop, find the real one |

Confirm arrival from the daemon's own log, not the client's output, and prefer a
**second independent counter** — a per-credential request/usage counter in the
daemon's management API proves *which* credential paid, which the client cannot tell you.

## 2. A silent hang forces fail-closed, everywhere

If a dead far end hangs, then "start the thing later / warn and continue / fall back to
the default" all convert a one-line stop into a whole run dying with no diagnostic. So:

- Ensure the hop is up **before** the first client launch, in the one place that already
  knows the whole batch and runs before every spawn.
- A misconfigured profile aborts that step — do not "warn and launch anyway". Silently
  falling back to the original vendor is the worst outcome: the work completes, the bill
  lands in the wrong place, and nothing in the transcript says so.
- Watch the inverse-report bug: an "everything is broken" set often has the same *shape*
  as "nothing is configured" (empty list). Check the error list BEFORE the empty-list
  early return, or the tool reports the exact opposite of the truth with a zero exit.

## 3. One daemon, many callers → refcount + ownership + age

A single localhost daemon serves the whole machine, so an unconditional stop at the end
of your run kills whatever else is mid-flight (silently, per §1) and destroys a daemon a
human started by hand minutes ago. Split the verb:

    <tool> daemon-down              # unconditional, for a human
    <tool> daemon-down --if-ours    # only when no claim remains AND we started it

- One claim file per run in a runtime dir; a `.spawned` marker written **only** when your
  code actually started the process (an already-running daemon gets a claim, never the marker).
- Prune claims by **age**, not by "not mine": a run killed mid-flight (OOM, reboot) leaks a
  claim that would otherwise pin the daemon open forever, but a genuinely long run must
  survive someone else's cleanup.

## 4. Generate their config, never edit their code

Emit the daemon's config file from your own store each run and treat theirs as an output.
Two traps:

- **Hot reload.** Assume the daemon re-reads its config while running (test it: rewrite the
  API key under a live daemon and re-auth). If so, regenerating with a fresh secret changes
  the key under a client that is mid-run — so make secret generation *idempotent*: create
  once, reuse forever, and have the health check name the mismatch explicitly.
- **Cost-fabricating keys.** A "force this model alias" style option can make the daemon
  rewrite the response's model id, so a cheap or plan-served request records as an expensive
  one and any local cost dashboard invents money. Assert your generator can never emit it,
  in the generator AND in a test — this class is undetectable downstream, because the
  recorded id is genuinely what came back.

## 5. Secrets belong in a 0600 file, never on the launch line

If the launch line is typed into a terminal multiplexer or shell, every byte reaches the
scrollback and `/proc/<pid>/cmdline` (world-readable, unlike `environ`). Put credentials in
the config/settings FILE, mask them in every read-only verb by default, and let only the
file writer see the real value. Two more: refuse the inline fallback when the payload
contains secrets (a write failure must stop, not downgrade), and `chmod` on **every** write —
`O_CREAT` does not tighten a file that already exists, so a store someone created by hand
keeps its loose mode with a token inside.
