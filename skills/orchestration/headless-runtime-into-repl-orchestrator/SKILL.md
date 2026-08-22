---
name: headless-runtime-into-repl-orchestrator
description: 'Use when adding a headless one-shot CLI agent (codex exec-style) as a worker to an orchestrator built for interactive REPL agents. Covers the dispatch seam, shell-injection guards, worktree…'
installer: auto-skill
created_at: 2026-08-22T22:48:32+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'orchestration'
content_hash: 49760bf1ad8a58a59e394778856d8ecd90190997848e0f9ff3db83d8c2a7b851
---
# Adding a headless (one-shot) agent runtime to a REPL-shaped orchestrator

Use when an orchestration engine was built around **interactive REPL agents** (open a pane, paste a
brief, read the TUI, nudge it) and you need to run a **headless one-shot CLI agent** (`<tool> exec …`,
runs to completion then the process dies) as a peer worker in the same run.

Every step below exists because skipping it produced a *silent* failure in a real integration.

## 0. Measure the runtime's real tool list BEFORE designing anything

Run one throwaway session and ask it to list every tool it can call. Do not infer from docs.

```
<runtime> exec -s read-only -C "$PWD" 'List the exact names of every tool you can call in this
session, one per line, nothing else.'
```

What you learn here decides the design, not the other way round. In one real case the runtime had
**no image tool at all**, which inverted a plan already half-built (see step 5).

## 1. Find the seam: it is DISPATCH, not LAUNCH

- REPL agent: launch opens the process, the brief arrives **later** via paste/send-keys.
- Headless agent: the brief arrives **with** the command (argv/stdin) and the process exits after.

So the only place the brief exists is wherever the engine composes it. Hook there.
Make the launch path **refuse** non-REPL runtimes loudly (`STOP:` + non-zero rc) rather than fall
through to the default command — falling through silently produces a worker that is quietly the wrong
runtime (wrong bill, wrong model, nothing reports it).

## 2. The command line is typed into a shell — treat it as an injection surface

Emit it from a **pure** function (no disk, no terminal) so tests can hit every case directly:

- single-quote every path; **reject** any path containing `'`, `"`, backtick, `$`, or a control char
- reject relative paths, path separators in identifiers, and runtime names outside `[a-z][a-z0-9-]*`
- **on every rejection, stdout must be EMPTY** — a leaked string gets typed into a live terminal.
  Write one test per rejection case asserting stdout `== ""`. This is the single most important test.
- persist the brief to a real file in the work dir and feed it on stdin (`- < brief`); a temp file
  that gets deleted leaves the agent unable to re-read its own instructions
- capture the true exit code: after `cmd | tee log`, `$?` is **tee's** status. Use `${PIPESTATUS[0]}`.
- wrap as `{ echo "runtime=<name>"; <cmd>; } 2>&1 | tee -a log` so the log **self-describes**: later
  stages usually know only (project, role) and cannot look up which runtime ran.
- append a terminal marker line (`…-exit=<rc>`) after the pipeline — this is your process-death signal.

## 3. Sandbox: a git worktree's `.git` is a FILE pointing outside the worktree

If the runtime sandboxes writes to its working root, it **cannot commit inside a worktree** without an
extra writable root for the real gitdir. And such flags usually only apply **at or under** the working
root — so set the working root to the **project**, not the worktree, and grant the project's `.git`.
Verify with a probe (`touch <gitdir>/x`) before blaming the agent.

## 4. Turn off every net that ends in "type into the pane"

Enumerate them; there are usually three (waiting-for-input detection, idle nudge, stall nudge). For a
headless runtime each one types into a **shell** whose agent has exited — the text then runs as a
command. Gate them on a predicate that later stages can evaluate from disk alone
(e.g. "the runtime log file exists"), because poll/verify functions rarely know the team config.

Replace them with the deterministic signal you now have: **exit-line present + completion marker
absent = terminal failure, report immediately.** Reuse the engine's existing failure-result *name* so
no routing table has to change. Report the tail of the log and explicitly say "do not send keys to this
pane". Real gain measured: 0s instead of burning the whole poll budget.

## 5. Completion marker alone is NOT completion

Measured: the marker file appeared **before** the commit; the poller returned success with uncommitted
work, and the agent committed seconds later. For headless you have a strictly better signal — require
**marker AND process-exit**. Do not apply this to the REPL runtime: its process never exits.

## 6. Translate the brief; do not let it order impossible things

Append a runtime-override block **after** the section carrying the anti-injection clause, so it wins on
both ordering and salience, and make it emit **nothing** for the native runtime (byte-identical
behaviour, and pin that with a test). Cover:

- **cwd**: usually different from the REPL agent's; state the real one
- **tool substitutions**: every `Skill(...)`, MCP call, or todo-panel API the brief mandates →
  a file-based equivalent (e.g. `LEARN:` lines in the notes file)
- **capabilities it lacks**: if it cannot do a gate honestly, **forbid it from writing that gate's
  evidence** and make the gate explain on stderr why its failure is *correct*. Handing it a paper path
  through the gate converts a real check into a ritual — that is worse than the gate blocking.
- **sub-agent spawning**: ban it. Agents it spawns are outside your accounting and cleanup.
- **one shot**: nobody can answer it mid-run, so blockers/assumptions must be written to disk *before*
  it finishes, and the completion marker must be the last write.

## 7. Ignore rules: `.gitignore` at the project root does NOT protect a worktree

A worktree checks out its own branch's `.gitignore`. Writing the project root's copy leaves your brief
and log as untracked files inside the worktree, and the protocol usually tells workers `git add -A`.
Write **`.git/info/exclude`** (resolve it with `git rev-parse --git-common-dir`): it lives in the common
dir, every worktree sees it, and `git add -A` never touches it. Do not write the worktree's tracked
`.gitignore` — the worker will commit it into the deliverable.
Test the **effect** (`git -C <worktree> status` shows nothing), not the file contents.

## 8. Cost accounting will silently read zero

Cost tables that sum the native runtime's transcripts will count a headless role as **0** and report the
run as cheaper than it was. Parse the runtime's own token line out of its log and print it where the
status of that role is read. If parsing fails print `?`, **never `0`** — `0` reads as "free".

## Verification order that actually catches things

1. unit-test the pure command builder (including every rejection → empty stdout)
2. dispatch through the engine with a **shim** that records what got typed into the pane
3. run it **live** in a real terminal with a tiny real task — steps 5, 7 and the cwd error only showed
   up live
4. run one sprint with both runtimes concurrently and merge both
5. **mutation-check** each new guard: disable it, confirm the matching test goes red
6. run the whole existing suite on a **frozen tree** — never edit source while a sweep is running, or
   you get phantom failures and have to redo it (this happened, twice)

Expect the two runtimes to pick different idioms (module systems, config files). Per-branch tests can
both be green while the merged trunk is red — check the trunk after merging, not only at the end.
