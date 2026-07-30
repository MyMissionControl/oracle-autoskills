---
name: refute-tool-token-win-claim
description: Use when re-testing a claim that an index/graph/search tool saves context vs grep+Read: rebuild the cheapest baseline, audit edge identity/direction not counts.
installer: auto-skill
created_at: 2026-07-27T20:11:23+00:00
created_session: 
trigger: reusable-workflow
created_by: skeptic-subagent
category: benchmarking
content_hash: 926940f62c7ec9ef1a4214131f81639d0da4a31497fe43dd2987f6afb1ce0a46
---
# Adversarially re-test a "tool X beats plain grep on tokens" claim

Use when someone reports that an index/graph/semantic-search tool saves context
vs plain `grep`/`rg`+Read, or when auditing such a benchmark. Two failure modes
dominate, and both make the tool look better than it is.

## 1. Rebuild the CHEAPEST competent baseline yourself

A benchmark's baseline is almost always naive: "locate the symbol, then Read
N-line slices" or "grep -B25". That pulls source text into context
unnecessarily. Before accepting any win:

- Ask what the tool's output actually *contains* (usually: symbol, file, line,
  and the enclosing scope name). Then produce exactly that with one command
  whose OUTPUT is small, even if it internally reads a lot. Output bytes are
  what enter context; internal reads are free.
- For "who calls X, from inside which function", a single awk pass over only
  the files that match gives caller + enclosing decl + true call line:

```
awk -v S="$SYM" '$0 ~ "^(export )?(async )?function |^(export )?const .*=.*=>" {f=$0; fl=FNR}
  index($0,S"(") && $0 !~ /^import/ {printf "%s:%d in %s (L%d)\n", FILENAME, FNR, substr(f,1,55), fl}' \
  $(grep -rl --include='*.<ext>' "$SYM(" <dirs>)
```

- Count the COMMAND text too, on both sides — the agent must emit it.
- Generalize before concluding: run the head-to-head on >=3 different symbols.
  A win or loss on one symbol is a lucky example, not a result.

## 2. Never trust an edge/relation count — check IDENTITY and DIRECTION

"N edges in, M edges out, so M-N were dropped" is arithmetic, not integrity.
Build sets of `(source, target, relation)` and diff them:

```
pa = {(s,t): {relations}} for input   # prefix ids the way the tool namespaces them
pm = {(s,t): {relations}} for output
dropped  = set(pa) - set(pm)
invented = set(pm) - set(pa)
reversed = [p for p in dropped if (p[1], p[0]) in pm]
```

If `len(reversed) == len(dropped)`, the tool is **inverting edge direction**,
not dropping edges — a silent wrong-answer generator that edge counts hide.
Also check for INVENTED nodes (output node count > sum of inputs) and for
nodes whose local id is absent from every input graph.

Then confirm direction against live source, not against another graph: find the
real call site line and the two declaration lines, and state which way the call
actually goes.

## 3. Separate staleness from tool limitation

When some indexes are older than the code:
- Measure index freshness independently: sample nodes, check the recorded line
  still contains that symbol in the live file (+/-3 lines tolerance). Report the
  eligible-node denominator; if eligible < sample size you did a census, say so.
- Run seed sensitivity (3-4 seeds). A single-sample percentage quoted to one
  decimal is usually optimistic; report the range.
- Then find at least one defect on a 100%-FRESH index. A bug reproduced on a
  fresh index cannot be excused as "just rebuild it", which is the tool
  advocate's standard escape.

## 4. Check "works" means correct CONTENT, not exit 0

- Verify every listed result 1:1 against ground truth, and hunt FALSE NEGATIVES
  (real call sites the tool omitted), not just false positives.
- Re-run once more for timing: if run 2 equals run 1, there is no warm-cache
  confound — say so explicitly.
- Re-run tie-broken commands (shortest-path etc.) twice. Differing output across
  identical invocations = non-determinism, itself a finding.

## Hygiene
Keep target repos pristine: scratchpad-only writes, `git -C <repo> status
--porcelain | wc -l` == 0 at the end, and confirm source index mtimes unchanged.
In a shared scratchpad, delete only the files you created.
