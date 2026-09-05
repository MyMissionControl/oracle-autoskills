---
name: attribute-regression-reds
description: 'Use when a long test suite goes red after you changed shared code — attribute each red to your diff or the baseline via md5-stamped isolated runs, red-set diffs, and pristine-worktree reproduction.'
installer: auto-skill
created_at: 2026-09-04T23:32:06+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'testing'
content_hash: c78ebf3e288e408510f823704877bdde25ace9233715093fd0d551e14448fba5
---
# Attribute regression reds to your change — or to the baseline

Use when a full test suite (dozens of files, tens of minutes) comes back with reds after you
changed shared code, and you must decide which reds are yours before committing. Guessing costs a
whole re-run; "it was probably already broken" is how a real regression ships.

## Run it where nobody can edit it

1. **Never run the suite against the live working tree.** Create a detached worktree at the base
   commit and copy in only your changed files:
   `git worktree add -f --detach <WORK>/wt-<tag> <BASE_SHA>`
2. **Stamp the file under test at both ends of the run:**
   ```
   echo "MD5_START $(md5sum <file> | cut -d' ' -f1)" >> "$R/summary.txt"
   ... run every suite ...
   echo "MD5_END   $(md5sum <file> | cut -d' ' -f1)" >> "$R/summary.txt"
   ```
   `MD5_START != MD5_END` ⇒ **throw the whole run away**. Another session edited the file mid-run
   and every red is unattributable. This happens on shared machines and is invisible otherwise.
3. Write one `summary.txt` line per suite (`name rc=N <pass/fail line>`) plus `fail-<name>.txt`
   holding `tail -60` of the output. Keep runs in numbered dirs — you will diff them.

## Attribute by the red SET, not the red COUNT

4. `awk '$2 !~ /rc=0/' regressN/summary.txt` for the current run **and the previous one**. Compare
   which suites and which assertion names are red — a count that stayed at 6 can still hide a swap.
5. **A suite that was green last run is not automatically your fault.** Reproduce it on a *pristine*
   worktree at the base commit with none of your changes, at comparable load
   (`cut -d' ' -f1 /proc/loadavg` — record it). Red there too ⇒ environment/baseline, not you.
6. **Check whether your diff can even reach it:**
   `git diff -U0 <file> | grep -E '^@@' | sed 's/.*@@ //' | sort -u`
   lists the enclosing function of every hunk. A red in code your hunks never touch needs a stated
   mechanism, not a hunch. Also grep your diff for the failing feature's keywords — a one-word
   insertion into a shared usage/dispatch string is a legitimate hit and easy to miss.
7. **Byte-compare the failure text between runs.** Identical text — including generated names and
   hashes — is a deterministic pre-existing failure. Cite that identity as the receipt.
8. **Timing flakes announce themselves two ways:** the assertion wording is a deadline
   (`fast (<Ns)`, `exits within`), and the red set *moves* between runs on the same code. Suites
   that drive real OS resources (a live terminal multiplexer socket, fixed ports, a browser) are
   where these live; they cannot be attributed from a single run.

## Before you commit

9. `pgrep -f '<runner>'` **matches the probing shell itself** — a "still alive" reading may be your
   own probe. Test liveness by reading `/proc/*/cmdline` instead.
10. Verify every file you are about to stage is byte-identical (md5) to what the run actually
    tested — including test files. Then stage explicitly by path, review `git diff --cached`, and
    state each surviving red with its attribution in the commit or the report.
11. Remove the worktrees you created (`git worktree remove --force`) and any `.bak` litter you
    dropped in the repo.
