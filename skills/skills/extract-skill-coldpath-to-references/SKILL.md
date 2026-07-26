---
name: extract-skill-coldpath-to-references
description: Use when a large always-loaded SKILL.md needs its context shrunk: extract cold rarely-hit sections to references/ (cat on demand), keep triggers+safety inline (L2->L3).
installer: auto-skill
created_at: 2026-07-20T03:24:08+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: skills
content_hash: 3d070ac7c38b0e31d7769dbb3871f1d0be3390f99054e5227725e7c261b2a3b8
---
---
name: extract-skill-coldpath-to-references
description: Use when a SKILL.md (or any long always-loaded instruction file) has grown large and you want to shrink its always-on context. Extracts rarely-hit "cold" sections into references/ loaded on demand via cat, keeping triggers + safety gates inline. Progressive-disclosure L2->L3.
---

# Extract cold-path sections from a large skill body into references/

Shrinks the eager/always-loaded body of a HOT skill by moving rarely-executed branches to `references/<name>.md` that are `cat`-ed only when that case is hit (Hermes L2->L3 progressive disclosure). Net win is context-window headroom (prompt cache softens raw token cost, so expect single-digit % byte reduction — the point is window, not $).

## When
- A `SKILL.md` (or similar always-loaded file) body is large and parts of it are only reached on rare branches (resume, error-recovery, teardown, opt-in modes).
- Do NOT use this for whole cold *skills* — moving an entire unused skill dir to a lazy MCP-served lib is a different mechanism (L1/L2). This is L2->L3 within one HOT skill.

## Steps
1. **Identify + analyze candidates (fan out if many).** Per block: cold-verdict (does a normal happy run ever enter it?), exact trigger condition, unique start/end anchor lines, every inbound cross-reference elsewhere in the file, any safety gate inside it. Add a global cross-ref pass to catch "see below"/step-id links that would dangle.
2. **Decide boundaries.** Keep INLINE: the trigger + any safety gate. Move OUT: only the detailed steps.
   - NEVER extract an executable control-flow arm that has no default handler (e.g. a bash `case` arm with no `*)`), or the runtime silently falls through when that token returns — a real correctness hazard (e.g. a fail-token with no arm = silent success). Keep such arms inline regardless of size.
3. **Extract with a script, not by hand.** Back up the file first (`.bak`). For each block: verbatim-slice start..end into `references/<kebab>.md`, then replace the block in-place with a short pointer that restates the trigger + key safety words + `cat "<abs>/references/<kebab>.md"`. Splice bottom-up (highest start line first) so earlier line numbers don't drift. Search the end-anchor starting AFTER the start line so an identical line elsewhere isn't matched.
4. **Keep inbound refs resolving.** If the pointer stays in-place with the same heading/marker/step-id, "see below"/step-id references still resolve — no edit to referrers needed.
5. **Adversarially verify (fan out).** (a) info-loss: diff backup vs (new body + all new refs) — every removed line must live in a ref or the pointer; (b) hot-path: a fresh happy run must stay fully executable inline, never forced to cat a new ref; (c) dangling: every cat path exists, inbound refs resolve, triggers+safety inline; (d) structure: code fences balanced, control-flow (case/if) intact; run the skill's tests.
6. **Commit only intended files.** Stage by explicit path (a big repo may have unrelated uncommitted work). Remove the backup before committing.

## Notes
- No window reload needed for body/reference edits (read fresh at invoke/cat). Reload only for L1 index changes (name/description edits, moving skill dirs in/out of the eager dir).
