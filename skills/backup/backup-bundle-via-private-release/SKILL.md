---
name: backup-bundle-via-private-release
description: 'Use when machine-local state (DB, dotfile dirs, crontab) must survive a cloud VM with no removable media: split by credential, ship clean set as a private GitHub Release asset, one-command verified…'
installer: auto-skill
created_at: 2026-08-20T08:11:06+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-code'
category: 'backup'
content_hash: 1246ff145be1917d2f6578c0c54503b61bbb89ca1a770f7814f99acae68a14e1
---
# Back up machine-local state off a box with no removable media

Use when a machine holds state that exists in **no git repo** (a DB, an app's dotfile dir,
hooks, crontab) and it must survive the disk — but the box is a cloud VM: no USB, no
`/media`, and any big temp mount is ephemeral. The route out is the network, and the
restore has to be one command a future you can run without remembering anything.

## 1. Prove what is ephemeral before choosing a destination

    lsblk -o NAME,SIZE,FSTYPE,MOUNTPOINT,LABEL
    head -3 /mnt/DATALOSS_WARNING_README.txt 2>/dev/null   # cloud temp disks say so themselves

A big free mount is not a backup target. Check for a warning file and for
`cloudimg`/ephemeral labels. Also check whether the editor is remote
(`ls -d ~/.vscode-server`) — if it is local, "download it in the IDE" moves nothing.

## 2. Split the bundle by credential, not by convenience

Scan every candidate, then keep two groups. Do not one-zip them: a single archive
containing one secret makes the **whole** archive un-hostable.

    # every text column of a DB, not just the obvious one
    # every file of an app state dir, minus rebuildable output
    grep -rlE 'sk-[A-Za-z0-9-]{10,}|gsk_|ghp_|github_pat_|AIza|xox[bp]-|-----BEGIN' <dir>
    grep -rhoE '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}' <dir> | sort -u

Two findings that repeat: keyword hits (`token`, `password`, `secret`) are usually **prose
in logs** describing an app, not credentials — read the context before condemning a file.
And the real secret is often **one tiny file** (`peer-key`, an oauth json). Excluding just
that file plus rebuildable build output moves a whole state dir into the clean group:

    tar -czf state.tgz --exclude='<dir>/ui' --exclude='<dir>/peer-key' -C / <relpath>
    tar tzf state.tgz | grep -cE 'peer-key|/ui/'    # must be 0 — verify the exclude worked

## 3. Ship the clean set as a **release asset**, never a commit

A large binary re-committed per snapshot bloats history forever and every clone pays.
Release assets stay out of git history.

    <stage-script> /tmp/off                 # copy + write SHA256SUMS + verify immediately
    gh release create <tag> -R <owner>/<repo> --title … --notes … /tmp/off/*

Two `gh` traps, both hit for real:
- an upload that **502s partway makes gh delete the half-made release**. Recover by
  creating it empty first, then `gh release upload <tag> <files> --clobber` (large asset
  in its own call).
- `gh release download` with **no tag requires `--pattern '*'`** — otherwise it prints
  usage and exits 1. A restore path that omits this fails on a fresh machine only.

## 4. Make restore one command, and verify before it touches live state

Teach the bootstrap script a `--restore-from <source>` sentinel that fetches by itself:

    gh release download ${TAG:+"$TAG"} -R "$REPO" -D "$D" --pattern '*' \
      && [ -f "$D/SHA256SUMS" ] && ( cd "$D" && sha256sum -c SHA256SUMS >/dev/null )

Order matters: **checksum first, then overwrite.** A truncated DB that silently becomes
the live memory is worse than no restore. Also:
- refuse to overwrite a bundle already present locally — the local one may be newer.
- in `--check`/dry-run mode, report and skip; do **not** count the normal state of a
  working machine as a FAIL (put the dry-run branch *before* the "already exists" branch).
- name in one line what a clean-only restore is still missing, and how to recover it
  (re-login, re-pair) — silence there reads as "complete".

## 5. Prove the round trip, not the upload

    rm -rf /tmp/rt && gh release download -R <owner>/<repo> -D /tmp/rt --pattern '*'
    ( cd /tmp/rt && sha256sum -c SHA256SUMS )
    # plus a format-level check on the big binary, e.g. sqlite PRAGMA integrity_check

`gh release view --json assets` showing `uploaded` is not proof the bytes are intact.

## Also

Deleting a credential from a config file does **not** revoke it, and if it has been read
by an agent it is now in append-only session transcripts that cannot be safely rewritten
— so rotate at the provider and treat file scrubbing as cosmetic. Probing a key from a
sandboxed tool call may be blocked by policy; hand the user the one-line curl instead.
When committing into a tree another session is editing, stage **only your own files** and
confirm with `git diff --cached --name-only`.
