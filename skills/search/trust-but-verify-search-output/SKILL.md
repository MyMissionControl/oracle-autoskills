---
name: trust-but-verify-search-output
description: 'Use when a code search returns 0 hits or garbled output before concluding a string does not exist: rg -r is --replace, and a hook may rewrite rg/grep/find.'
installer: auto-skill
created_at: 2026-08-08T16:28:03+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'subagent-file-writer-trace'
category: 'search'
content_hash: 664f4319cf932b86ac08e76a5f5613fb43c8719f1c6fa5a4ece1b317768d8a1b
---
# Trust-but-verify grep/rg output before concluding "not found"

Use when a code search returns 0 hits (or garbled hits) and you are about to
conclude a string does not exist anywhere. A false-negative search sends the
whole investigation down the wrong path.

## Two silent corruptions, both real

### 1. `rg -rn` is NOT "recursive + line numbers"
In ripgrep `-r` is `--replace`, so `-rn PATTERN` parses as `--replace n` and every
matched span is printed as the literal `n`:

```
# looks fine, is lying:
rg -rn 'Files changed' .      ->  file.ts:12:      `n: ${x}`
```

ripgrep is recursive by default — there is no `-r` to add. Same trap:
`-rnF` silently drops `-F` and you get `regex parse error: unclosed character class`
on a pattern like `concepts: [commit`, printed to stderr where a `> out.txt`
redirect hides it.

Rules:
- never pass `-r` to rg; write `rg -n -F`
- always capture stderr too: `rg ... > $S/out.txt 2> $S/err.txt` then check `err.txt`
- print `rc=$?` and `wc -l < out.txt` on the same line so "0 hits" and "crashed"
  are distinguishable

### 2. A PreToolUse hook may rewrite your command to a token-saving proxy
Some setups rewrite `rg`/`grep`/`find` into a compressing CLI proxy. Symptoms:
`/usr/bin/grep: unrecognized option '--hidden'`, line numbers that do not match the
file, a `diff -q` that says DIFFERENT for identical files, or output that is a
summary rather than the real lines.

Fixes, in order:
1. call the binary by absolute path: `/usr/bin/rg`, `/usr/bin/find`, `/usr/bin/diff`
   (`command -v rg` tells you the path)
2. redirect to a file and open it with the file-Read tool — the proxy only
   filters what goes to stdout, not what lands on disk
3. verify any suspicious grep hit by Read-ing the file at that offset before
   quoting it in a conclusion

## Procedure for "find the code that writes THIS artifact"

1. Read one real artifact verbatim; note every distinctive literal, including the
   body, not just the frontmatter (body templates are rarer than key names).
2. Search fixed-string, most distinctive first, widening the root each round:
   `/usr/bin/rg -n -F -e '<exact literal>' <roots> > out.txt 2> err.txt`
3. If a whole-home sweep is needed, exclude the artifacts themselves so the
   generator is not buried: filter the result file (`grep -v '/<vault-dir>/'`)
   rather than pre-excluding, so you can still confirm the sweep found anything.
4. Do not stop at the directories the task named. A generator that runs on every
   commit usually lives in a hook (`~/.config/git/template/hooks/*`,
   `.git/hooks/*`), not in the app that consumes its output.
5. Template dirs are copied at `git init`/`clone` only: the fixed template and the
   installed copies can disagree. `find <tree> -path '*/hooks/<name>'` and diff each
   against the template to know which version actually produced old artifacts.
6. Confirm the match by re-deriving the artifact's own filename from the code
   (slug rules, cut widths, date format). If the filename reproduces exactly,
   you have the writer — not merely a lookalike.
