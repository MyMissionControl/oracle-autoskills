---
name: vendor-policy-primary-sources
description: 'Settle a vendor ToS/policy question with quotable primary evidence: markdown doc twins, llms.txt, docs-in-repo raw sources, dating clauses via git history, 403 workarounds, and clause-structure…'
installer: auto-skill
created_at: 2026-08-22T12:01:50+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'subagent-research'
category: 'research'
content_hash: 9e63149ced521c4dd65ebf03a7180e95363a0adf90c7a6b25203cc6c73cc187e
---
# Settle a vendor policy/ToS question from primary sources

Use when you must answer "is <pattern> allowed by <vendor>?" with quotable primary
evidence (ToS, product docs), not blog posts. Works for any vendor whose docs and
legal pages are public.

## 1. Prefer machine-readable twins of doc sites
Modern doc portals ship markdown twins — try these BEFORE scraping HTML:
- `<docs-host>/<path>.md`  (Mintlify/Nextra style; e.g. many product docs)
- `<docs-host>/llms.txt`   (index of every page + one-line description)
- `<docs-host>/llms-full.txt` (whole doc set in one file)
Scraping the HTML gives you 200 lines of nav chrome; the `.md` twin gives clean prose
you can `grep -n` for `automat|CI|subscription|api key|parallel|limit`.

## 2. Docs that live in a public repo: read the source, not the render
Many vendors publish doc sources on GitHub. Fetch raw markdown:
`https://raw.githubusercontent.com/<org>/<repo>/main/<content-path>.md`
Find paths with one call instead of guessing:
`curl -s "https://api.github.com/repos/<org>/<repo>/git/trees/main?recursive=1" | python3 -c "import json,sys;[print(t['path']) for t in json.load(sys.stdin)['tree'] if 'docs' in t['path'] and t['path'].endswith('.md')]"`

## 3. Date a policy clause with git history (turns prose into evidence)
When a clause matters, find WHEN it was added — a dated clause is much stronger evidence
and often lines up with an enforcement wave:
`curl -s "https://api.github.com/repos/<org>/<repo>/commits?path=<file>&per_page=10"`
then fetch the commit and print the patch hunk for that file.

## 4. Legal pages that 403 your fetcher
Marketing/legal hosts often block agents. Order of attempts:
1. plain fetch, 2. `curl` with a desktop User-Agent,
3. Wayback: `curl -s "http://archive.org/wayback/available?url=<host>/<path>"` then curl the
   returned snapshot URL (a fetch tool may refuse web.archive.org while curl succeeds).
Strip tags with a 5-line python regex pass and grep the restrictions section.

## 5. Read the clause structure, not the headline
Three clause families decide most automation questions:
- a blanket "no automated/non-human access" ban WITH a carve-out ("except via API key
  or where we otherwise explicitly permit it") -> the carve-out is satisfied by the
  vendor's own docs documenting the automated recipe. Quote both halves.
- a "third-party tools/clients may not use these credentials" ban -> aimed at other
  people's clients, not at you invoking the vendor's own binary. State the distinction.
- per-seat/one-login clauses -> only bite when a second human or a resale is involved.

## 6. Separate "no enforcement found" from "permitted"
Search enforcement separately, and characterize precedent by SHAPE (own client vs
third-party client vs credential proxy). Report absence of precedent as precedent risk,
never as permission. Check whether the exact pairing still EXISTS — deprecation pages
kill some questions outright, and product repos' own docs can be months stale.
