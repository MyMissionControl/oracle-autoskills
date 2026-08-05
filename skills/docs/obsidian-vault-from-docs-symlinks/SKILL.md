---
name: obsidian-vault-from-docs-symlinks
description: 'Use when a repo''s docs must be browsable in Obsidian but opening the folder as a vault shows thousands of files: per-file symlinks + Dataview frontmatter, safe prune, force which vault opens.'
installer: auto-skill
created_at: 2026-08-05T16:02:08+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude-opus-5'
category: 'docs'
content_hash: 94cd034834eabf871df91b5af23a9ee3b1be737f17ec1f679f2b65a2de5ab02e
---
# Curated Obsidian vault over an existing docs tree (symlinks, no copies)

Use when someone wants to browse a repo's / workspace's markdown docs in Obsidian and
"just open the folder as a vault" produces thousands of files or an unreadable flat list.

## Why the obvious approaches fail

1. **Vault root = the repo/workspace.** Obsidian has NO ignore mechanism (`.obsidian`
   has no ignore file; "Excluded files" only dims *search* results, the explorer still
   lists everything). Every `node_modules/**/README.md` becomes a note. Measure first:
   ```bash
   find <root> -name '*.md' | wc -l                              # what Obsidian will show
   find <root> -path '*/node_modules/*' -name '*.md' | wc -l      # the flood
   find <root> -name '*.md' -not -path '*/node_modules/*' -not -path '*/.git/*' | wc -l
   ```
   A 20:1 ratio is normal. This alone kills the one-symlink-per-project idea.
2. **One symlink for the whole project dir** — same problem, it drags the flood in.
3. **Generated notes that link OUT to real files** (`file:///…`). Simple and safe, but
   `[[wikilinks]]` only resolve INSIDE the vault, so those links bounce the reader out
   to their editor. Fine if they only want an index; useless if they want to read in Obsidian.
4. **Copying the docs in.** Goes stale, and edits made in Obsidian are lost on regen.

## The shape that works

```
<vault-root>/
  .obsidian/                        seeded config + plugins (see below)
  <One Top Folder>/
    <One Top Folder>.md             folder note: index + a Dataview query
    <unit>/                         one folder per project/module/unit
      <unit>.md                     GENERATED summary note (frontmatter = the query surface)
      README.md      -> symlink to the real file
      <loose docs>   -> symlink per file
      wiki           -> symlink to the real docs subfolder (folders are fine)
      sprint/NN.md   -> symlink per file, RENAMED so it sorts
```

Per-file symlinks (not one per unit) buy two things: you choose exactly what appears, and
you can **rename on the way in**. Obsidian sorts alphabetically, so `thing-10.md` lands
before `thing-2.md` — zero-pad when linking (`String(n).padStart(2,"0")`).

## Non-obvious mechanics

- **Frontmatter is the whole point of the generated note.** Real project docs usually have
  none, so Dataview has nothing to query. Emit `status`, counts, percent, `updated`, and
  `tags: [<ns>/<kind>]`, then query `FROM #<ns>/<kind>`. Verify with
  `grep -c '^<marker>' <vault>/**/*.md` that every generated note carries a marker line.
- **Escape the alias pipe inside tables**: `| 1 | [[note\|Title]] | date |`. An unescaped
  `|` splits the cell. Strip `|`/`[`/`]` out of any title you interpolate.
- **Ship the plugin offline.** Community plugins are plain files (`main.js`,
  `manifest.json`, `styles.css`). Copy them from a vault that already has it — find one by
  reading the app's own vault registry — and write `community-plugins.json` = `["<plugin>"]`.
  No network, no manual install step.
- **Selecting which vault opens.** Apps like this remember a "last used" workspace; a bare
  launch reopens it and ignores your new folder. Merge into the registry
  (`~/.config/<app>/<app>.json`, `vaults: {<id>: {path, ts, open}}`) instead: keep every
  other entry, set `open:false` on them, `open:true` on yours. Derive the id as
  `sha256(realpath).slice(0,16)` so re-running never duplicates the entry, and fold away any
  pre-existing entry with the same path under a different id. Write tmp + `rename()` so a
  crash can't leave a half-written registry, and **no-op on a corrupt/missing file** —
  opening the wrong vault beats destroying the user's list.
- **A GUI instance already running will only get focused**, still showing the old workspace.
  Detect it (`pgrep -f -i <app>`) and tell the user to switch or restart; do not pretend.

## Prune without destroying the originals

The generator must be able to drop units, and this is where a naive `rm -rf` eats real work.
Rules that make it safe, all testable:

- Only `unlink()` entries that are symlinks (`lstat().isSymbolicLink()`), never recurse INTO
  a symlinked dir.
- Only delete regular files that carry your own marker line in their frontmatter — a
  hand-written note in the vault survives.
- `rmdir()` dirs only when already empty. Never `rm -rf`.
- If a real file sits where a symlink belongs, skip it and report; never clobber.
- If the link target vanished between plan and write, skip it — no dead links.

Split the module `plan(units) -> {dirs, links, notes}` (pure, no writes) and
`write(plan, root)`, so the whole layout is unit-testable without a filesystem fixture.

## Verify for real before claiming it works

```bash
find -L <vault>/<Top>  -name '*.md' | wc -l          # what the reader actually sees
find -L <vault>/<Top>  -path '*node_modules*' | wc -l # must be 0
find    <vault>/<Top>  -xtype l | wc -l               # dead symlinks, must be 0
find <real-root> -name '*.md' -not -path '*/node_modules/*' | wc -l   # unchanged before/after
```
Also assert in tests: writing through a symlink lands in the real file, and pruning a unit
leaves that unit's real docs byte-identical.
