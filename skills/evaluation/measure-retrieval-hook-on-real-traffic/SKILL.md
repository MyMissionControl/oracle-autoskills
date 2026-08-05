---
name: measure-retrieval-hook-on-real-traffic
description: 'Use when judging whether an auto-injection hook really helps, or before tuning its ranker. Builds the eval from logged model decisions, not hand-written queries.'
installer: auto-skill
created_at: 2026-08-05T13:31:46+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'claude-opus-5'
category: 'evaluation'
content_hash: ad4f11bdc25954dfc3140f1a6c1dbc446fe064fc6e0e0880a16cabdd7ac975ca
---
# Measure whether an auto-injection hook actually helps, on real traffic

Use when you have built (or inherited) something that automatically injects
suggestions into an agent's context — a retrieval hook, a RAG preamble, a
"relevant docs" sidecar — and you need to know whether it earns its place.
Also use before tuning its ranker: without this, tuning optimizes a fiction.

The failure this prevents: reporting a healthy-looking accuracy number that was
produced by an evaluation you wrote yourself, for a mechanism that in production
has never once fired on a real request.

## 1. Never trust an eval you authored

Queries written by whoever is tuning the ranker measure agreement with that
person's mental model of the corpus. That is the one variable they cannot be
neutral about. Expect a 3x gap: one such eval scored 87% acc@1 where a
transcript-derived eval scored 24% on identical code.

Derive ground truth from decisions that already happened. In an agent harness
the richest source is the transcript log: a turn where the MODEL chose to invoke
a capability. The preceding request is the query, the thing it reached for is
the expected answer.

## 2. Filter the harvest, or the numbers invert

Each of these silently corrupts the measurement:

- **Sub-agent turns.** In most harnesses a spawned agent's prompt is logged with
  the same record type as a human's, distinguished only by a flag
  (`isSidechain` or equivalent). Missing it once turned a 5% fire-rate into 60%
  — one fan-out of 31 agents outnumbered every real prompt.
- **Machine-generated text shaped like a request**: task notifications, tool
  results, compact/continuation summaries, system reminders, hook output,
  slash-command echoes. Nobody typed them.
- **Dictated calls.** If the request literally contains the capability's name,
  that is not retrieval, it is transcription. Exclude, and count separately —
  the ratio tells you how much autonomous routing is really happening.
- **Non-requests that happen to precede a call**: "yes", "continue", banners.
- **Targets outside the index.** Anything exempt by design (plugin-provided,
  vendored) scores as a miss and measures nothing.

Log every filter's count. A filter that drops most of the corpus is itself the
finding.

## 3. Replay the real prompt stream, not just the eval

The eval set is self-selected: every entry led to a capability being used, so it
over-represents requests the mechanism was built for. Separately, take the last
N requests actually typed since deploy and run the hook over each. Report
`fired / total` and, for every silent one, WHY it was silent, bucketed:
below-threshold, no tokens, too short, filtered.

Quote both numbers and label them. "Fires on 5% of all requests" and "fires on
68% of requests that warrant a capability" are both true and describe the same
hook; using the flattering one unlabelled is the lie.

## 4. Read the results split by input class

Aggregate accuracy hides class failure. Split by whatever your corpus and your
users differ on — most commonly **language**. A latin-only tokenizer against an
operator who writes another script produces a whole bucket that scores exactly
zero, invisible inside a healthy-looking mean.

If one class is dead, say so plainly and identify whether the fix is on the
query side, the corpus side, or both. A tokenizer that segments the query does
nothing when every document is still in the other language.

## 5. Freeze the set before touching the ranker

Persist the harvested pairs to a file and re-score BEFORE and AFTER every change
to tokenization, weights, or scoring parameters. Three cherry-picked examples
are not evidence: one such "clean win" raised three test prompts and dropped
overall recall@3 from 100% to 93%.

If the pairs contain user text, gitignore the frozen file and commit only the
generator — it rebuilds locally in seconds, and prompt history should not leave
the machine to make an eval reproducible.

## 6. Separate what you proved from what you plumbed

Infrastructure wins (smaller always-on context, no truncation, one code path,
a duplicate-generating bug fixed) are real and stand on their own. They are NOT
evidence that retrieval improves selection. Report them in different sentences.

## Checklist

- [ ] eval derived from logged model decisions, not hand-written
- [ ] sub-agent turns excluded
- [ ] synthetic/machine-generated prompts excluded
- [ ] dictated calls excluded and counted separately
- [ ] out-of-index targets excluded
- [ ] real prompt stream replayed, silence bucketed by cause
- [ ] both fire-rates quoted with their denominators
- [ ] results split by input class (language, length, locale)
- [ ] pairs frozen to a file; before/after scored on the same file
- [ ] user text gitignored, generator committed
- [ ] infrastructure wins reported separately from retrieval quality
