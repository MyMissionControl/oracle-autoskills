---
name: probe-tui-inflight-states-zero-quota
description: 'Use when you need the exact frames an API-backed TUI draws mid-request (spinner/elapsed footer), e.g. a busy-vs-idle grep looks wrong: freeze it with a hanging endpoint, sample tmux, fixture it.'
installer: auto-skill
created_at: 2026-08-11T15:07:34+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude-opus-5'
category: 'tui-automation'
content_hash: 94caca803b714bb37335a929924e6d65896b94b07d2de9fe7bd40238db3e3d41
---
# Probe a TUI's in-flight states with zero API cost

Use when you must know **exactly** what an API-backed TUI draws *while a request is in flight*
(spinner text, elapsed-time footer, progress glyphs) — typically because a supervisor/automation
greps that region to decide "busy vs idle" and you suspect the pattern is wrong.

Do **not** guess from memory, and do not grep the shipped binary: modern CLIs are compiled
bundles (bun/deno single-file) where `strings` finds nothing.

## Why the obvious routes fail

| Route | Why it fails |
|---|---|
| `strings <binary> \| grep 'esc to interrupt'` | compiled/compressed bundle → 0 hits even though the string renders |
| grep the agent's own transcripts | pane captures are usually not stored in transcripts |
| run a real task and screenshot | you catch the *steady* state, not the first seconds — and it costs quota |

The hard part is the **early window**: many TUIs show one shape before the first token/byte
arrives and a richer shape after (token counters, throughput). Supervisors almost always match on
the *rich* shape, so the early window is where false "idle" hides.

## Procedure

1. **Freeze the in-flight state** by pointing the client at an endpoint that accepts the
   connection and never answers. Zero quota, and the state lasts as long as you want:

   ```python
   # blackhole.py — accept, read, then hold forever
   import socket, threading, time
   s = socket.socket(); s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
   s.bind(("127.0.0.1", <PORT>)); s.listen(16)
   def hold(c):
       try: c.recv(65536); time.sleep(600)
       except Exception: pass
   while True:
       c, _ = s.accept(); threading.Thread(target=hold, args=(c,), daemon=True).start()
   ```
   Prefer this over an unroutable/refused address: a refused connection triggers retry/error
   banners instead of the steady in-flight render.

2. **Run the TUI in a real pty** — `tmux new-session -d -s probe -x 120 -y 40 "<ENV_BASE_URL>=http://127.0.0.1:<PORT> <cli>"`.
   ⛔ Never pipe it (`| tee`): with stdout not a tty the TUI does not render and you capture nothing.
   Start it in a directory the tool already trusts, or first-run onboarding prompts eat the screen.

3. **Submit work, then sample fast.** Send the text and the Enter key as **separate** `send-keys`
   calls with a short settle between — one combined call is commonly swallowed by TUI composers.
   Then loop ~50-100 captures at ~0.25 s, appending only the lines you care about:

   ```bash
   for i in $(seq 1 70); do
     tmux capture-pane -p -t probe:0 | grep -nE '<candidate glyph/keyword pattern>' >> frames.txt
     sleep 0.25
   done
   sed -E 's/^[0-9]+://; s/[0-9]+/N/g' frames.txt | sort -u    # distinct shapes, times normalised
   ```
   Normalising digits collapses hundreds of frames into the handful of real shapes — including the
   animation's full glyph cycle, which a single screenshot would miss.

4. **Save a full frame as a test fixture**, not just the matched line: geometry (how deep the line
   sits under boxes/footers) is often part of the bug, so a one-line fixture cannot regress it.
   ⛔ Match the suite's fixture-naming contract — suites often glob a directory and derive the
   expected verdict from the filename suffix; a new capture named freely asserts the wrong answer.

5. **Tear down by PID, never by pattern.** `pkill -f "<cmd>"` can match the very shell running it
   and kill your cleanup mid-way; take the pid from `ss -ltnp` / `$!` and verify the port is free.

## Turning the finding into a pattern (the part that bites)

- Add a **new alternative**; never rewrite the existing ones. Old builds/other machines still draw
  the old shapes and they cost nothing to keep.
- **Anchor on structure the idle state cannot have.** An idle screen usually keeps a similar-looking
  line (same glyph, past tense, "took 3m 40s") — so require the in-flight-only token, e.g. the
  ellipsis *plus* a parenthesised running clock `(<n><h|m|s>`.
- Decide which error is worse and bias that way. For a "still working?" probe, **false-busy is
  usually worse than false-idle** — a waiter that never returns beats a nudge that arrives a second
  late. Say so in the comment, with the accepted cost.
- ⛔ Put multi-byte glyphs in an **alternation** `(·|✻|✽)`, never a bracket class `[·✻✽]`: under
  `LC_ALL=C` a bracket of multi-byte chars degrades into single bytes and over-matches. Run the
  fixture matrix under both the normal locale and `LC_ALL=C` and require identical verdicts.
- Prove no false positives on real negatives: every existing idle fixture must stay idle, plus a
  synthetic line of ordinary prose/bullets ending in the same punctuation.

## Before blaming your change for a red suite

Stash your edit and re-run the failing suite. A suite can be red from **state leaking between its
own cases** (an earlier case mutates the fixture a later case reuses) — fix the isolation and say
plainly that it was pre-existing.
