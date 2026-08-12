---
name: prove-streaming-reader-rewrite
description: 'Use when swapping readFile+split for a streaming line reader in trusted (billing/metrics) or UI-thread code: prove the line sequence is identical and measure the freeze with an external observer.'
installer: auto-skill
created_at: 2026-08-12T20:38:16+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'opus5-main'
category: 'perf'
content_hash: 126eb2f66f60e7631b06b2c48807f603d9d4c2e6858d85b948e39970e97edced
---
# Prove a streaming rewrite of a hot file reader

Use when replacing `readFile`/`readFileSync` + `split(/\r?\n/)` with a streaming reader in code
whose output someone trusts (billing, metrics, aggregates) or whose thread someone watches (a UI
host). Two things must be proven, and the obvious way to measure each one is wrong.

## 1 — Prove the OUTPUT is unchanged, without re-implementing the math

Do not diff the aggregate. Diff the **line sequence**, which is the only thing the rewrite touches:

1. Copy the new reader verbatim into a throwaway script (keep it byte-identical to the shipped one —
   sync it with a script, don't retype it).
2. For every real input file, hash the sequence of lines the consumer actually keeps
   (apply its own filter, e.g. `line.indexOf('"usage"') !== -1`) under BOTH readers.
3. Assert equal count and equal hash. Same lines in the same order ⇒ the downstream fold is
   unchanged by construction, and you never had to reproduce its pricing/aggregation logic.

Run it over the **whole real corpus**, not a fixture. Report files, bytes, and mismatches.

Edge cases the hash will catch if you get them wrong: a trailing line with no final newline; `\r\n`
(the old regex dropped the `\r`, a naive `indexOf("\n")` keeps it); an empty final chunk.

## 2 — Measure the freeze with an EXTERNAL observer

- **An in-process sampler (`setInterval` + `process.memoryUsage().rss`) cannot see inside a
  synchronous block** — the timer never fires, so a sync reader reports a *small* peak and looks
  better than the async one. Zero samples during the work is not a small footprint; it IS the
  freeze signal (and is worth asserting deliberately: old = 0 ticks, new = N ticks).
- For the real peak, run each variant as its own process under `/usr/bin/time -v` and read
  **Maximum resident set size**. Alternate old/new/old/new a few times; single runs are noisy.
- Isolate phases: if the same script also did a corpus-wide pass first, its garbage inflates the
  perf phase. Gate the phases on an argv flag.

## 3 — Stream BUFFERS, not strings

`createReadStream(file, { encoding: "utf8" })` then `leftover + chunk` is a trap: rope
concatenation plus V8 sliced strings that **retain their parent**, so it can peak HIGHER than
`readFile` did. Instead:

- read Buffers, `Buffer.concat([leftover, chunk])`, scan for `0x0a`
- decode each complete line with `buf.toString("utf8", start, end)` → an independent string
- `leftover = Buffer.from(buf.subarray(start))` — **copy**; a subarray view pins the whole chunk
- `0x0a` never appears inside a multibyte UTF-8 sequence, so splitting there cannot cut a codepoint

Yield between files (`await new Promise(r => setImmediate(r))`) if the caller is on a UI thread.

## 4 — Know when NOT to go incremental

Resuming from a stored byte offset is the bigger win and is often unsafe: check whether the
consumer keeps **per-file** dedupe state (a `seen` set over ids). If it does, resuming mid-file can
re-count a record the earlier pass already counted. For billing that means double-charging. Say in
the commit message that you rejected it and why, or someone will "optimize" it later.
