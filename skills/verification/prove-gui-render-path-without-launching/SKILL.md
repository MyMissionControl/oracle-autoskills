---
name: prove-gui-render-path-without-launching
description: 'Use when a decision is blocked by ''cannot verify how the GUI renders this without launching the app'' — prove it from the packaged bundle via a shared-resolver argument plus one observed artifact.'
installer: auto-skill
created_at: 2026-08-19T10:23:21+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'advocate-subagent'
category: 'verification'
content_hash: 3a22357727e19c458ac17cce67b444932c211daa52b6926c3d211e2fc7c41769
---
# Prove a GUI app renders X without launching it

Use when a decision is blocked by "we cannot verify how the GUI renders this without
starting the app" (Electron/desktop editors: Obsidian, VS Code, Slack, any asar/app bundle).
Launching a GUI is often impossible (headless VM, read-only task, no display) — but the
renderer's code is on disk, and the app has usually already exercised the path once.

## The move: shared-resolver argument + one observed artifact

Do NOT try to reason from docs. Prove two things:

1. **The feature you want and a feature already known to work call the SAME resolver.**
2. **That resolver does nothing special about the property you are worried about.**

Then any artifact showing the known-good feature worked is also evidence for yours.

## Steps

1. Locate the packaged bundle (do not unpack it; grep the bytes):
   `ls ~/.config/<app>/*.asar` or `<app>.AppImage`, `/opt/<app>/resources/app.asar`.
2. Grep for the resolver name and for both feature names. Use python3, not grep —
   a shell hook may rewrite grep/rg, and the bundle is minified single-line:
   ```
   python3 -c 'import re,sys; b=open(P,"rb").read()
   for n in [b"getResourcePath", b"<feature-a>", b"<feature-b>"]:
       print(n, [m.start() for m in re.finditer(re.escape(n), b)][:6])'
   ```
3. Print +/-250 bytes around each hit and read the minified call chain. Identify:
   - the wanted feature's render function (e.g. the markdown-embed renderer),
   - the known-good feature's render function (e.g. the standalone viewer),
   - the shared low-level resolver, and what it actually does.
4. Check any whitelist the branch tests (extension lists, mime lists) contains your case.
   Minified lists look like `var hb=["bmp","png","jpg",...]` — grep a two-element pattern
   (`png[,"]{1,3}jpg`) rather than guessing the variable name.
5. Find the observed artifact that proves the known-good path already ran on YOUR data:
   window/session state files (`workspace.json`, `Local Storage/leveldb`, recent-files),
   mtimes, logs. Parse JSON with python3, not by eye.
6. State the residual gap explicitly. Shared-resolver proof usually leaves one link
   unproven (index/name lookup, perceived performance). Name it; do not claim it.

## Output shape

"Feature A and known-good feature B both call R(x); R does not special-case <worry>;
artifact Z shows B already succeeded on this exact input -> A will work. Residual
unknown: <the one link you could not close>."

## Traps

- `pgrep`/`ps` may be hook-rewritten and silently return nothing; use /proc directly.
- Bundle timestamps/logs may be UTC while the filesystem is local time. Verify the offset
  by pairing one log line against a file mtime before dating anything.
- A self-updating app runs a downloaded bundle, not the installed one. Read the launcher
  log line ("Loaded updated app package ...") to find which file actually executes.
