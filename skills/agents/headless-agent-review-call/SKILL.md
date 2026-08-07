---
name: headless-agent-review-call
description: 'Use when wiring an agent-review button via headless claude -p and the call hangs, times out, or returns unparseable output'
installer: auto-skill
created_at: 2026-08-07T09:02:46+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude'
category: 'agents'
content_hash: dc25e0fdff0b390dd8d60ddc297b94ddd8b24225bd680508b3bac1dbfbf8b47b
---
---
name: headless-agent-review-call
description: Use when wiring a "have an agent review this text" button into an app via headless `claude -p` (or any CLI agent) and the call hangs, times out, or returns unparseable output — covers interview-style skills that never terminate headless, tool-wandering, model latency, and output contracts.
---

# Headless agent review call that actually returns

A UI button that says "let an agent check this" is a **single-turn text
transform**: text in, structured result out. Four things break it, in this
order. Diagnose in this order too — each later step is wasted if an earlier one
is still true.

## 1. Never name an interactive skill in a headless prompt

Interview/interrogation skills exist to run a live back-and-forth. Their text
typically says some variant of:

- "ask the questions one at a time, **waiting for feedback** before continuing"
- "**do not** enact the plan until I confirm"
- "if a question can be answered by exploring the codebase, **explore the
  codebase instead**"

Headless there is nobody to answer, so the run waits and/or wanders. Symptom:
the process produces **no stdout at all** and never exits, while a trivial
prompt on the same binary round-trips in seconds.

**Check before you trust a skill name in a prompt:**

```bash
head -40 ~/.claude/skills/<name>/SKILL.md   # or wherever skills live
```

Grep for "wait", "one at a time", "until I confirm", "explore". If present:
**do not invoke it** — copy its *stance* into your prompt as plain
instructions, and add explicit counter-instructions:

```
⛔ do not ask back in the output, do not wait for an answer,
   do not read files or explore the codebase, do not call any tool.
   Put the questions you want to ask in the `questions` field of the JSON.
```

Add a unit test that asserts the prompt does **not** contain the skill name —
this regresses easily when someone "improves" the prompt later.

## 2. Turn the tools off

Nothing in a text transform needs a tool, and tools are an invitation to wander.

```
--disallowedTools Bash Read Glob Grep Edit Write WebFetch WebSearch Task Skill
```

Note this also disables skill loading — which is fine, because step 1 already
inlined what you needed.

## 3. Close stdin

Spawn with stdin **ignored**, not piped. A piped-but-never-written stdin turns
any prompt the CLI decides to ask into a permanent hang:

```js
spawn(BIN, ["-p", ...flags, "--", prompt], { stdio: ["ignore", "pipe", "pipe"] })
```

## 4. Measure model latency BEFORE choosing the timeout

Do not pick a timeout from intuition, and do not inherit the session's default
model. Long output in a non-Latin script is dramatically slower, and the
frontier model may not fit any reasonable UI timeout at all.

```bash
# baseline — is the binary itself healthy?
time <BIN> -p "reply with exactly: PONG" < /dev/null

# the real prompt, one run per model tier
for m in haiku sonnet opus; do
  echo "== $m"; time timeout 300 <BIN> -p --model $m <flags> -- "$(cat prompt.txt)" < /dev/null | head -c 200
done
```

Pin the tier that fits your ceiling, as a **per-process flag** (this does not
touch the user's global model setting). Record the measured numbers in a
comment next to the constant, with the date — otherwise the next reader
"simplifies" the pin away.

Then make the wait visible: a label frozen for two minutes reads as a dead
button. Tick elapsed seconds and say that clicking again cancels.

## 5. Parse defensively, and refuse empty rewrites

The same prompt returns bare JSON on one tier and a ```json fence on another —
observed on the *same* prompt across tiers. Preambles ("Here is the review you
asked for:") also happen. Try, in order: the whole output, the fenced block,
then the widest `{` … `}` span. Never throw.

Then **reject a result whose payload field is missing or empty**. Treat it as a
parse failure, not an empty rewrite — otherwise a malformed reply silently
blanks the user's document.

## Verification that this actually works

Static checks prove nothing here. Run the real binary end to end and assert on:

- elapsed seconds (against your timeout)
- parse succeeded
- the payload is non-empty and shaped right
- **round two**: feed answers back and assert the answers appear in the output
  and the answered questions are **not** re-asked; assert a skipped (empty)
  answer never reaches the prompt
