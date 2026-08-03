---
name: differential-test-tool-corruption
description: Use when someone challenges a claim that a tool/step corrupted data, or before making that claim: re-run the transform on its own inputs and diff as multisets to establish causality.
installer: auto-skill
created_at: 2026-08-03T09:14:50+07:00
created_session: 
trigger: user-correction
created_by: claude
category: verification
content_hash: 42157a2e0edb80f3b9629b98dcf05ca232b557db1aa7c50724d00e2d11719a94
---
---
name: differential-test-tool-corruption
description: Use when someone challenges a claim that "tool/step X is what corrupted the data" — or you are about to make that claim. Establishes causality by re-running the transform on its own inputs and diffing the output against them, instead of citing an old measurement.
---

# Prove a transform is the corrupter (differential test)

Claims like "merging broke the direction", "the importer dropped rows", "the migration
reversed the mapping" are usually recorded as a bare number in a note. A bare number
cannot answer "how do you know it was that step?" This is the cheap experiment that can.

## Why this works

If the inputs are byte-identical files you still have, and the transform is the only
step between them and the output, then any difference between output and input is
attributable to the transform. No baseline reconstruction, no history archaeology.

## Steps

1. **Pin the inputs.** Use the exact stored artifacts, not regenerated ones. If you must
   regenerate, you have lost causality — say so.
2. **Re-run the transform now**, on the current tool version. Record version + wall time.
   Old numbers may predate a fix; the point of the test is that it is cheap to redo.
3. **Diff as multisets, not counts.** Counts hide swaps. Build a comparable tuple per
   record — for a graph `(source, target, relation)`, for rows a natural key + payload —
   then compute:
   - `lost   = inputs - output`
   - `gained = output - inputs`
   - **`reversed = |{t in lost : flip(t) in output}|`** ← the tell. If `lost ≈ gained ≈
     reversed`, nothing was dropped; orientation was scrambled. Counts alone look perfect.
4. **Normalize ids correctly, and verify the normalization.** Transforms often re-key
   (`<tag>::<id>`, prefixes, surrogate keys). A wrong strip makes 100% of records look
   changed. Sanity gate: if `lost == len(inputs)`, your normalization is broken, not the
   tool. Print two raw ids from each side before trusting any diff.
5. **Decide which side is wrong using ground truth outside both.** Compute the answer
   independently (hand-rolled traversal, a `grep`/`awk` pass, a SQL count) and check the
   real source for one concrete record. "They differ" is not "the output is wrong."
6. **Measure the user-visible consequence,** not just the internal delta. Run the actual
   query/report both ways and compare against ground truth. "37% of edges flipped" lands
   much harder as "the answer went from 173 correct to 31 plus 9 invented."
7. **Find the mechanism, then label it.** Look for a declared property that makes the
   corruption inevitable (an undirected type, a set instead of a list, a dict keyed on a
   non-unique field). State it as measured only if you read it; otherwise write
   "inference, not measurement."
8. **Retract what did not reproduce.** Old claims that fail to reproduce must be named and
   withdrawn in the same breath as the confirmed ones, or the next reader keeps citing
   them.
9. **Test more than one input pair.** Small/large, homogeneous/heterogeneous. Rates that
   vary by pair (18% vs 29% vs 37%) tell you it is order-dependent, not a fixed bug.

## Scale of the fix

If the corruption is only in the tool's transform and the data itself carries what you
need, hand-writing the transform is often ~20 lines and strictly more correct. Test it
against the same ground truth before adopting it.

## Anti-patterns

- Citing the old note instead of re-running. The re-run is usually seconds.
- Comparing counts and declaring the data intact.
- Diffing without proving your key normalization.
- Explaining the mechanism before measuring the effect (you will explain a bug that no
  longer exists).
