---
name: adopt-shared-tool-default-safely
description: 'Use when making a tool/generator CHOOSE a config it currently only honours (shared package store, new lockfile, new runtime): find the real first-write seam from git history, convert post-hoc, pin…'
installer: auto-skill
created_at: 2026-08-29T15:57:08+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude-code'
category: 'tooling'
content_hash: d7271a0b375067114a85eb8a3c6959625bfe1fea1eac77261dfddb8025c7a34e
---
# Turn a tool's "reactive" default into a proactive one without breaking live consumers

Use when a shared tool/generator only *honours* a config it finds (a lockfile, a marker, a field)
and you must make it *choose* that config for new work — while N existing consumers keep working.
The trap is not the new behaviour; it is that your new default silently rewrites someone's
production project on its next run.

## 1. Find where the artifact is actually first created — from history, not from the code

Grep tells you which code paths *could* create it. Only history tells you who *did*.

    cd <a real generated project>
    rtk proxy git log --format='%h %ad %s' --date=iso --reverse | head
    rtk proxy git log --diff-filter=A --name-only -- '*<the artifact>'   # earliest add
    rtk proxy git log -1 --name-only <that sha>                          # who else came with it

If the artifact first appears in a commit made by an agent/human rather than by the tool, **there
is no pre-emptive seam**. Look for a gap: tool's init commit at T0, artifact at T1, no tool verb in
between → anything you add before T1 runs when the file it needs does not exist yet.

Then classify every candidate call site as RUNS vs PRINTS:

    # RUNS: executes the command                PRINTS: emits it into a script/yaml/README
    rtk proxy grep -n '<the command>' <tool>    # then read each hit and label it

Only a RUNS site can change reality; a PRINTS site changes what someone else will run later. You
usually need both, and they are different edits.

## 2. Close the "just tell the agent to do it" option explicitly

Before writing a mechanism, prove the cheap path is dead — otherwise a reviewer will ask:

    rtk proxy grep -c -i '<the tool name>' <every prompt surface: SKILL.md, references/, heredocs>
    # and check the size gate that guards those files
    bash tests/<size-or-thinness-suite>.sh   # a ceiling with ~no headroom = you cannot add text

A prompt instruction is also LLM-compliance-dependent. If either the ceiling or compliance is a
problem, say so in the commit message; it justifies the heavier mechanism.

## 3. Prefer post-hoc conversion over pre-emptive choice

Converting *after* the artifact exists needs no seam before it, and preserves what the first tool
pinned. Look for the tool's own import/convert verb (`pnpm import`, `pip freeze`, `X migrate`).
Measure it on a throwaway fixture with 2-3 tiny real deps — never a big one:

    ( cd $FIX && <old tool> install )     # produce the original artifact
    ( cd $FIX && <new tool> import )      # convert
    diff <(list versions from artifact A) <(list versions from artifact B)

**Order matters when the new tool's version is itself ambient.** Read the running version FIRST,
convert with it, and pin *that* version afterwards. Pinning first and then failing to convert
leaves a config field that lies about the project.

## 4. Never trust an ambient tool version — pin from what the repo declares

Modern launchers (corepack-style shims, asdf, mise) resolve the version from mutable machine state
outside the repo. A CI runner has none of that state.

    readlink -f "$(command -v <tool>)"    # a shim, not a binary?
    <tool> --version                      # can change under you between runs

If the artifact format is versioned, check what happens across a major boundary **in both
directions** — many tools refuse both newer and older artifacts. That refusal is what turns
"install the tool" into "install exactly this version".

## 5. Verify against the ONE real production consumer before shipping

This is the step that saves you. Enumerate consumers, rank by blast radius, and test the highest
one **read-only** by copying its manifests out:

    mkdir -p $S && cp <consumer>/<manifest files> $S/ && mkdir -p $S/node_modules  # fake deps dir
    <tool> <the verb that now transforms things> $S
    ls $S     # did the new artifact appear where it must NOT?

If the transformation is unreachable for that consumer for an incidental reason (no build script,
etc.), add the missing precondition locally and re-run — otherwise you have proven nothing.

## 6. Guard by structural property, not by name

A hardcoded exclusion list rots. Find the *property* that makes the consumer unsafe (a workspace
declaration the new tool cannot read, a platform-specific artifact, a differing config file) and
gate on that — it protects consumers you have not met yet. Add a named opt-out marker as a second
layer, and put the marker in whatever ignore-list every other marker of that tool lives in, so it
cannot trip a dirty-tree gate.

    if <has property the new tool cannot handle> && [ ! -f "$d/<new tool's own config>" ]; then
      echo "SKIP $d (<why, in one line the reader can act on>)"; return 0
    fi

## 7. Gate the downstream artifact too

If the tool also PRINTS commands into CI/deploy config, the new tool must be installed there.
Check the runner image's actual software list before assuming:

    WebFetch https://raw.githubusercontent.com/actions/runner-images/main/images/<os>/<Image>-Readme.md

Then add a gate that fails when the generated config calls a tool the image lacks — scoped to the
tools that are genuinely absent, or you ship a false positive on the one that ships preinstalled.

## Traps that cost real time

- **A `no`-style assertion ("must NOT contain X") passes on the old code too.** Red-proofing only
  proves the `has`-style ones. Count them separately and say so, instead of claiming every new
  assertion was red.
- **A guard placed after another writer is unreachable.** If helper A always creates the file that
  guard B checks for, B's negative branch can never be tested through that path. Reach it by making
  the write fail (`chmod 444`), and say in the test comment why that is the realistic case.
- **Appending to a config with `>>`** breaks a file whose last line has no trailing newline — and it
  often breaks only ONE of the two tools that read it, so it looks like the other tool's bug.
  Guard with `[ -n "$(tail -c1 "$f")" ] && printf '\n' >> "$f"`.
- **Regenerating a lockfile is only safe in one state.** With the new tool's installed tree present
  and flat, the old tool reads the tree and agrees; with the tree absent it re-resolves to newer
  versions; with a symlinked/virtual-store tree it walks into internals and writes a poisoned
  artifact that still passes the old tool's own verify. Precondition-check all three.
