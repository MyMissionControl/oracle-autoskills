---
name: prove-isolation-layer-removable
description: 'Use when deciding whether to remove a cage/sandbox around a vendored tool — prove safety empirically first and check the guard covers the real entry point.'
installer: auto-skill
created_at: 2026-08-31T15:45:00+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude'
category: 'tooling'
content_hash: df8045cc9ee82d3d066429ef0b9d8040d0154b22409825af01c683aefaac1054
---
---
name: prove-isolation-layer-removable
description: Use when deciding whether to remove a cage/sandbox/isolation layer around a vendored third-party tool (fake $HOME, chroot, separate config dir) — prove empirically it is safe before removing, and check the guard covers the real entry point.
---

# Prove an isolation layer is removable before removing it

An isolation layer around a vendored tool (`HOME=<cage>`, `--config-dir`, a container) buys
protection but usually costs a **split state store**: the tool's own data moves with the
knob, so every config exists twice and must be hand-synced. Before defending or removing
one, settle two questions with measurements, not argument.

## 1. Does the tool actually write the protected path?

Build a throwaway home that mirrors the real one **including the valuable content** — an
empty fake proves nothing, because most tools create-if-missing and no-op when present.

```bash
SP=<scratch>/probe; rm -rf "$SP"; mkdir -p "$SP/h/<protected>/{sub1,sub2}"
cp <real>/<protected>/<big-config>  "$SP/h/<protected>/"     # real bytes, not a stub
snap() { find "$1" \( -type f -o -type l -o -type d \) -printf '%y %p\n' | sort; }
sums() { find "$1" -type f -exec md5sum {} \; | sort -k2; }
snap "$SP/h/<protected>" > before.tree; sums "$SP/h/<protected>" > before.md5
HOME="$SP/h" <tool> <the-exact-subcommand-you-ship>
snap "$SP/h/<protected>" > after.tree;  sums "$SP/h/<protected>" > after.md5
diff before.tree after.tree; diff before.md5 after.md5      # both empty = no-op
```

Diff **tree and checksums separately**: tree alone misses in-place rewrites, md5 alone
misses new/removed paths and symlinks. `find -type f` does not list symlinks — add
`-type l` or you will "prove" a symlink absent that is right there.

## 2. Is the guard on the door people actually use?

List every entry point and grep each **module** — not the whole package — for the protected
path:

```bash
grep -n "<protected>\|<PathVar>\|<DangerousClass>" <pkg>/<cmd-you-spawn>.js   # expect 0
grep -rn "<DangerousClass>\|<destructive-fn>" <pkg> | grep -v <that-module>   # the real risks
```

Then ask which entry points the cage covers. A cage over the *dashboard* while the *CLI*
already runs uncaged is guarding the safe door. Check the sibling launchers/wrappers'
defaults — the risky path is often already open and has already been used (look for backup
files the destructive command leaves behind, dated before today).

## 3. Separate the two kinds of guard

- **Ships with your product**: hardcoded argv (`args: [entry, "config"]`), an allowlist in
  code. Every user inherits it. Pin it with a test asserting the forbidden subcommands are
  unreachable.
- **Machine-local**: a blocklist in a hand-made wrapper on one box. Real protection, but it
  does not travel. Say so explicitly rather than counting it as coverage.

## 4. Migrate the split store before flipping the switch

Removing the layer strands whatever lives on the isolated side.

- Back up **both** sides first, plus the wrapper script.
- Grep for consumers that reference entries **by name** before renaming anything
  (`grep -rn '"<id>"' <state-dirs>`) — a sidecar binding a name is a silent breakage.
- Merge in the vendor's own natural format only; never invent fields.
- Verify with **the vendor's own reader** (`<tool> list`), not your parser.

## 5. Order of operations

backup → migrate + verify with vendor's reader → move the guard → change your code →
update tests → typecheck/compile → run the vendor's reader **and** your reader live →
commit → delete the old side last.

Keep the deleted layer's rationale in the code as a comment saying *why it went* and what
must never come back, plus a test that fails if it does (`expect(keys).toEqual([...])`,
`expect(SRC).not.toContain("<cageVar>")`). A removed guard with no note gets re-added by
the next person who reads the original design doc.

## Pitfalls

- **Deleting a directory containing a symlink into the real tree**: `unlink` the symlink
  explicitly first and count the target's entries before *and* after. `rm -rf` does not
  follow symlinks, but proving it beats trusting it.
- **Blaming your change for pre-existing test failures**: check whether the failing file
  imports anything you touched, and check machine load — shell-out tests with fixed
  timeouts fail under load, not from your diff.
- **Reading state from a doc instead of the running system.** The doc records the decision;
  only the live files record what is true now.
