---
name: prove-index-links-two-domains
description: 'Use when a graph/index tool is claimed to connect two artifact domains (docs<->code, tests<->code): settle it with cross-domain edge counts, mixed connected components, and a planted probe corpus…'
installer: auto-skill
created_at: 2026-08-17T11:26:42+07:00
created_session: 
trigger: 'complex-task'
created_by: 'subagent'
category: 'analysis'
content_hash: f4ba4710aaaa8a1295c0d8bc281b7be253b9ff4df42193fbd38a374554f137be
---
# Prove whether an index/graph actually LINKS two domains

Use when a tool claims (or is hoped) to connect two kinds of artifact — docs↔code,
tests↔code, config↔code, tickets↔commits — and you must settle it with receipts
instead of counting nodes. Node counts lie: a domain can be 27% of the nodes and
still be a disconnected island.

## The trap

`<domain> nodes: 460 (9.5%)` reads like coverage. It is not. Presence of nodes
proves ingestion, never connection. The decisive quantity is **cross-domain edges**
and **mixed connected components**, which almost no tool reports.

## Procedure

### 1. Read the extractor before the data
Find the per-extension dispatch table (`EXTRACTORS = {".md": ...}` or similar) and
open the extractor for the secondary domain. Answer three questions from source:
- which extensions route here,
- what node types it emits,
- **what the allow-list for link targets is.**

That allow-list is usually the whole answer. A doc extractor with
`LINKABLE_EXTS = {".md", ".rst", ".txt"}` can never emit a doc→code edge — code
extensions are excluded by construction.

Distrust docstrings. Cross-check every claimed edge type against actual
`add_edge(...)` call sites:
`grep -n 'add_edge\|"references"\|relation=' <extractor>`
A docstring promising "references code symbols" with one `add_edge` in the file
is a stale docstring, not a feature.

### 2. Classify every edge by ENDPOINT TYPE, not by relation name
Relation histograms hide this. Bucket each edge by what its two endpoints are:

```python
byid = {n['id']: n for n in g['nodes']}
def dom(n): return 'B' if (n.get('source_file') or '').endswith(SECONDARY_EXTS) else 'A'
cnt = collections.Counter()
for l in g['links']:                      # note: JSON graphs often use 'links', not 'edges'
    s, t = byid.get(l['source']), byid.get(l['target'])
    if not s or not t: cnt['DANGLING'] += 1; continue
    cnt[dom(s) + '->' + dom(t)] += 1
```
`A->B` and `B->A` at zero ends the discussion.

### 3. Connected components — the claim that cannot be argued with
Count components containing BOTH domains. Report the largest component's
composition too.
```python
# undirected adjacency over resolvable edges, then flood fill
mixed = sum(1 for c in comps if has_A(c) and has_B(c))
```
"0 of N components contain both" is the strongest single receipt available.

### 4. Planted probe corpus (proves the MECHANISM, not just this dataset)
Build a tiny corpus in a **scratch dir** where the secondary artifact references
the primary through *every* mechanism you can think of — relative path link,
bare filename, backticked symbol, prose mention. Run the real build command.
If it still emits zero cross edges, the gap is structural and no amount of
better-written docs in the real repo will close it.

Then confirm with the tool's own query surface:
`<tool> path "<doc node>" "<code node>"` → expect "No path found".

### 5. Separate coverage from connection
These fail independently — measure both:
- **coverage**: compare in-index files against `git ls-files '<glob>'`. Many
  indexers silently honour .gitignore, so gitignored vaults/memory dirs are 0%
  indexed while tracked files are 100%.
- **outside-the-index prose**: count the same artifact type in stores that have
  no index at all (`~/.<agent>/skills`, memory dirs, ungraphed sibling repos).
  Report `inside / (inside + outside)`.

### 6. Beware seed-matching masquerading as traversal
A `query` command may return both domains and look like it connected them. It
usually seeded on **label string match** and expanded each seed inside its own
island. Disprove it with step 4's `path` check between the two returned nodes.

### 7. Price the one capability that survives
If the secondary domain reduces to a structural outline (headings, symbols),
benchmark it against the trivial baseline and report bytes both ways:
`grep -E '^#{1,6} ' file | wc -c` vs the tool's `explain` output.
Being 2.5x larger than grep, while requiring a multi-MB index, is a finding.

## Reporting rule
Lead with the cross-domain edge count and the mixed-component count. Give every
number its command. "It has doc nodes" is not an answer to "does it link docs to
code".
