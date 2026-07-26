---
name: commit-live-code-exclude-dead-prototype
description: Use when committing a feature whose untracked files mix live code with an abandoned prototype; trace the import/asset graph to stage only live files, gitignore dead heavy dirs, verify build.
installer: auto-skill
created_at: 2026-07-24T06:17:59+00:00
created_session: 
trigger: reusable-workflow
created_by: claude-code
category: git
content_hash: cad3f308de6b3de3728699cc3c5078716555b54e5ed04395de64e5cea5af64d7
---
---
name: commit-live-code-exclude-dead-prototype
description: Use when committing a feature whose untracked files mix live code with an abandoned prototype (heavy vendored/native dirs, orphan scripts). Trace the import/asset graph to stage only what the live entrypoint loads, gitignore the dead heavy dirs, verify the build.
---

# Commit live code, exclude the dead prototype

When a working tree has many untracked files and some are an **abandoned prototype**
(vendored libs, native build trees like node-pty, orphan JS), do NOT `git add .`.
A wrong sweep can commit tens of MB of dead native code. Separate live from dead by
tracing the actual dependency graph, not by guessing from filenames.

## Steps

1. **List candidates.** `git status --porcelain | grep '^??'` for untracked; note
   sizes of any suspicious dirs: `du -sh <dir>`. A big native/vendored tree is the
   red flag.

2. **Find the live entrypoint(s).** The tracked/modified files are what the build
   actually uses. Grep which untracked modules they import:
   `grep -rn "<untracked-basename>" <src-of-tracked-files>`.

3. **Walk the graph transitively.** For each newly-required untracked module, grep
   its own imports and which runtime asset it loads
   (`asWebviewUri`, `require`, `<script src>`, `joinPath(... , "x.js")`).
   Keep only files reachable from a live entrypoint. Everything else is dead.

4. **Confirm the dead files are truly orphaned.** `grep -rn "<dead-basename>"` across
   src + assets returns nothing live (a mention only inside another dead file, or a
   stale comment, does not count).

5. **Stage precisely.** `git add -u` for tracked mods, then `git add <each live
   untracked file>` explicitly — never a whole dir that mixes live+dead.

6. **Gitignore the dead heavy dirs** so a future `git add .` can't sweep them:
   append `/path/to/<vendored>/` and `/path/to/<native-tree>/` to `.gitignore`.
   Leave small orphan files unstaged (visible in status) or let the owner delete them.

7. **Prove the split.** `git diff --cached --stat` shows only intended files;
   `git status --porcelain | grep -v '^[MAD]  '` should list ONLY the dead leftovers.

8. **Verify build before commit** (e.g. `tsc -p ./ --noEmit`, `bash -n <script>`),
   then commit + push.

## Gotchas
- Two generations of the same feature can coexist in one asset dir — only the file the
  live host actually loads is real; sibling `*-grid.js` / `*-old.js` are dead.
- If a tracked file imports an untracked live module, they MUST commit together or the
  build breaks — you cannot split them across commits.
