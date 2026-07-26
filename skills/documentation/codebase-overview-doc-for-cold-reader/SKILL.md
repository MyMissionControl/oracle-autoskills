---
name: codebase-overview-doc-for-cold-reader
description: Use when writing an overview/PROJECT_CONTEXT doc a reader will read WITHOUT the codebase: map via parallel agents, draft, then validate with a sandboxed cold-reader sub-agent.
installer: auto-skill
created_at: 2026-07-21T01:51:31+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: documentation
content_hash: 726300b9e5379ea5bbe92f62463ec10d4cdf7d9deb096e59bad74747fd190a8c
---
# Codebase overview doc for a context-free reader

## When
Asked to produce a PROJECT_CONTEXT / onboarding / architecture-overview doc that will be **read by someone (or some LLM) that cannot see the codebase** — e.g. pasted into a web chat to discuss the project. Not for normal in-repo docs where the reader has the code.

## Procedure
1. **Confirm scope first** if the target is a multi-repo workspace or otherwise ambiguous ("whole ecosystem" vs one app). One AskUserQuestion — scope changes the entire deliverable, so don't guess.
2. **Explore the ACTUAL code, not memory/assumptions.** For a large/multi-component target, fan out parallel read-only Explore agents (one per major component/repo). Give each the SAME structured brief: purpose · tech stack · folder structure · key modules + how they wire · one end-to-end data flow · data model · non-obvious rules · fragile spots · "flag anything you're unsure about." Handle small/peripheral parts yourself. Read config + entry points + README first.
3. **Draft.** Sections that transfer well to a cold reader: a 30-second TL;DR at the very top; what/why; tech stack; folder layout; components + how they connect; the main end-to-end data flow; data model; non-obvious domain rules; fragile spots / tech debt / known issues; roadmap (pull from plan/todo/req files); a glossary; and a consolidated "known unknowns" list. Use prose (not bare one-word bullets). Mark every uncertainty explicitly ("not sure") instead of guessing. Don't paste long code — summarize what it does.
4. **Cold-reader test (the key, non-obvious step).** Dispatch ONE sub-agent that may Read ONLY the finished doc — explicitly forbid it from opening/searching/globbing any other file (this sandboxes it into the real reader's position). Have it (a) answer 8-10 realistic reader questions using only the doc, tagging each CLEAR / PARTIAL / NOT-ANSWERED, and (b) critique: ambiguity, jargon used before it's defined, questions the doc fails to answer, internal contradictions, and a top-N ranked list of fixes.
5. **Apply the findings.** Recurring real gaps to expect: no "how to install / run" section; an overloaded term used before it's disambiguated; jargon introduced long before the glossary; a "has a server vs has no server" confusion between components; missing as-of date + no consolidated unknowns.
6. **Summarize in chat**; don't force the user to open the file. Offer a condensed 1-page variant and/or a translation if length/language matters.

## Notes
- The sandboxed cold-reader agent is what catches blind spots the author is too close to see. Do not skip it for a doc whose entire purpose is to be read without the code.
- Place the doc where the user expects (usually repo/workspace root, e.g. PROJECT_CONTEXT.md).
- A strong first-round result (most questions CLEAR) is normal — still apply the critique's ranked fixes; a second round is optional and usually confirmatory.
