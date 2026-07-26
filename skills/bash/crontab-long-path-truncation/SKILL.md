---
name: crontab-long-path-truncation
description: Use when 'crontab <file>' fails with a mangled/truncated path error even though ls/cat on that path work — fixed-size argv buffer, fix by installing from a short /tmp path.
installer: auto-skill
created_at: 2026-07-26T08:09:38+00:00
created_session: 
trigger: error-recovery
created_by: claude-code
category: bash
content_hash: abc2ce5312855f31d3d8ff7560d1861b08fe9df1de81aef570852716dc5533ac
---
# crontab silently truncates long file paths — install via a short /tmp path

`crontab <file>` (cronie/vixie-cron) has a fixed-size internal buffer for its
argument. Pass a path longer than roughly 100 characters (e.g. a deep session
scratchpad path) and it fails with a mangled, truncated error like:

    /tmp/claude-.../some-long-dir/scratch: No such file or directory

Note the printed path is cut mid-word ("scratch" instead of "scratchpad/foo") —
that truncation, not a real missing file, is the tell. This reproduces
identically whether invoked directly or via a proxy/wrapper (e.g. rtk proxy),
ruling out a hook/proxy rewrite as the cause.

Fix: copy the crontab file to a short path first, then install from there.

    cp "$LONG_PATH/crontab.new" /tmp/crontab_install.txt
    crontab /tmp/crontab_install.txt
    rm -f /tmp/crontab_install.txt

Applies generally to old C CLI tools with fixed argv/path buffers — if a
command fails claiming a file is missing but `ls`/`cat` on that exact path
succeed, suspect argument-length truncation and retry from a short path
(e.g. bare /tmp/<name>) before chasing hooks, permissions, or race conditions.
