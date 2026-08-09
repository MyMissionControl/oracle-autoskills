---
name: prose-as-machine-contract-audit
description: 'Use when a gate or pipeline greps its own tool''s human-language message to decide a verdict: find the real cases, prove the fragility, swap to a token while keeping a legacy reader, TDD both ends.'
installer: auto-skill
created_at: 2026-08-09T00:55:29+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5-session'
category: 'correctness'
content_hash: 3cf597657c7ed06879f9fdde59549513a45194e45885fbe351d7086065a9bdc6
---
# Audit: prose used as a machine contract

Use when a pipeline/gate reads its own tool's **human-language message** to decide a verdict
(any language, any tool). Symptom class: rewording one `echo` silently flips a gate to its
pass value — no error, no failing test.

## 1. Find the real cases, not the noise

Strip comments first, then keep only lines where the natural-language string sits inside a
**predicate**, not inside output:

```bash
python3 - <<'PY'
import re
NL=re.compile(r'[฀-๿]')          # <- swap for the script range you audit
PRED=re.compile(r"(grep\s+-[a-zA-Z]*[qcE]|case\s+.*\sin\b|=~|\[\s*\"?\$)")
for i,l in enumerate(open("<engine>.sh",encoding="utf-8",errors="replace"),1):
    s=l.rstrip(); t=s.lstrip()
    if t.startswith("#") or not NL.search(s) or not PRED.search(s): continue
    print(i,t[:160])
PY
```

Then classify every hit by **who reads it**:

| reader | verdict |
|---|---|
| machine parses it | **bug** — must become an ASCII/English token |
| a human writes it AND a human reads it, code only *heals* it | **correct, leave it** |
| value assigned then only printed (never compared) | **false alarm** |

The third and second categories are the majority. Check the assigned-value case by grepping
every `case "$var"` / `[ "$var" = ` for that variable before calling it a bug.

## 2. Prove the fragility — never assert it

Feed the *would-be* new wording into the **old** matcher and show the miss:

```bash
printf '%s\n' "TAG: 7 findings"  | grep -qE 'TAG: [0-9]+ <native-word>' && echo HIT || echo MISS
```
A MISS here is the whole argument. Also confirm the current writer output still HITs, so you
know the contract works today and you are fixing fragility, not a live outage.

## 3. Fix: token first, prose after

```
writer:  TAG: FINDINGS=<n> — <n> <native prose for the human> · <rest>
         TAG: NOT_SCANNED — <native prose> …
reader:  grep -qE 'TAG: FINDINGS=[1-9]|TAG: [0-9]+ <native-word>'
         grep -qE 'TAG: NOT_SCANNED|TAG:.*<native-not-scanned-word>'
```

⛔ **Keep the legacy pattern in the reader.** Artifacts already on disk from past runs carry
the old wording; a reader that only accepts the new token turns those into the *pass* value
silently — you would replace a latent bug with a real regression.

⛔ Put the "this token is machine-read, do not translate" warning on the **writer** line, not
only in a design doc. The next person edits the `echo`, not the doc.

## 4. TDD both ends of the contract

Write these RED first — the missing guard is why the fragility existed:

- writer emits the token **and** still carries the human prose
- reader accepts the **new** token
- reader accepts the **legacy** prose form
- the findings form is **not** misread as the not-scanned form (both strings coexist on one line)
- the clean/empty form maps to neither

Assert with the shell builtin `[[ "$out" == *"$want"* ]]`, not `printf | grep -q`
(grep exits at first match → SIGPIPE → under `set -o pipefail` a match reports failure).

## 5. Don't sell it as a token saving

Measure before claiming cost: comments in a script are cold path and cost **nothing**, so most
non-ASCII mass in an engine is free. This is a **correctness** fix. Say so.
