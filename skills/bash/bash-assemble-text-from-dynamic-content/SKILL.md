---
name: bash-assemble-text-from-dynamic-content
description: Assembling multi-line bash text from dynamic content with backticks or dollar-paren? Use quoted heredoc + placeholder + bash substitution, not unquoted heredoc/printf.
installer: auto-skill
created_at: 2026-07-22T06:11:48+00:00
created_session: 
trigger: error-recovery
created_by: claude-code
category: bash
content_hash: 27620a6509dfbc1e5a30d07c2794ba014bb65529f6fc82b92cd66e8c8ba6fb47
---
# Assembling multi-line text from dynamic content in bash

## Problem
Unquoted heredoc (`cat <<EOF`) and `printf '%s' "$var"` both let backticks/`$()` be
interpreted by the shell. With unquoted heredoc, **literal** backticks you wrote in the
body can pair ACROSS LINES and run as commands (e.g. a table cell `` `%h` `` + a later
`` `- [ ]` `` line → runs `- [ ]` → `line N: -: command not found`). Values injected via
`$var` expansion are NOT re-scanned (safe), but literal backticks in the body ARE.

## Fix — quoted heredoc + placeholder + bash substitution
```bash
body="$(cat <<'TMPL'
- **Worker:** {{WORKER}}
| Commit | msg |
{{COMMITS}}
- Follow-up: ห้าม `- [ ]`
TMPL
)"
body="${body//\{\{WORKER\}\}/$worker}"      # bash replace: value literal, no re-parse
body="${body//\{\{COMMITS\}\}/$commits}"    # multiline value OK; backtick/$()/& all literal
printf '%s\n' "$body"
```
- `<<'TMPL'` (quoted delimiter) = NO expansion at all — backticks stay literal
- `${var//find/replace}` = replacement is literal (unlike sed: no `/` or `&` pitfalls); injected values are never re-parsed

## Debugging discipline (systematic)
1. Reproduce with CLEAN input first (no special chars). If it still errors, the trigger is
   LITERAL body text, not input — bisect the literal content, not the inputs.
2. `printf` does NOT fix a literal-backtick problem — args are interpreted the same as an
   unquoted heredoc. Only the quoted heredoc (`<<'X'`) avoids interpretation entirely.
3. Verify the fix by re-running the reproduce (stderr must be empty) AND the existing tests
   (no regression), before committing.
