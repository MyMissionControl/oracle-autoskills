---
name: prove-local-webui-capability
description: 'Settle whether a local web dashboard can do X (vs needing its CLI) by driving headless chromium over CDP and attributing server routes to the module they actually call'
installer: auto-skill
created_at: 2026-08-24T01:37:03+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'claude-opus-5'
category: 'debugging'
content_hash: 9a73813902456a207fdf503ff120cc6035a9f2e7a49ee6c2a9874cce3beb0e9a
---
---
name: prove-local-webui-capability
description: Use when settling "can this local web dashboard do X, or does X need the CLI?" — read the real UI by driving headless chromium over CDP, then attribute each candidate server route to the module it actually calls. Catches route names that look like the feature but belong to a sibling subsystem.
---

# Prove what a local web UI can and cannot do

Asking a bundled SPA "is there a button for X?" by grepping its minified assets gives false
negatives (labels live in i18n chunks) and false positives (a route named after the feature
may drive a different subsystem). Settle it from both ends: what the page renders, and what
the server can reach.

## 1. Run the app the way its own launcher does

Copy the launcher's invocation (entry file, env, HOME overrides) instead of inventing one —
`tr '\0' ' ' < /proc/<pid>/cmdline` and `tr '\0' '\n' < /proc/<pid>/environ | grep ^HOME=`
on an already-running instance is the cheapest source of truth. Note the port it prints; a
dashboard that probes `[3000, 3001, ...]` lands on a different port when one is taken.

## 2. Read the rendered page, not the bundle

`--dump-dom` with a virtual-time budget, piped (never redirected to a file: a snap-packaged
chromium discards stdout to regular files), then strip tags:

    chromium --headless --no-sandbox --disable-gpu --password-store=basic \
      --virtual-time-budget=15000 --dump-dom http://127.0.0.1:PORT/route 2>/dev/null \
      | sed -n '/<body/,$p' | python3 -c "import sys,re,html; s=re.sub(r'<(script|style|svg)[^>]*>.*?</\1>','',sys.stdin.read(),flags=re.S); [print(l) for l in dict.fromkeys(html.unescape(x).strip() for x in re.sub(r'<[^>]+>','\n',s).split('\n')) if l]"

Collect the sidebar/nav text first: nav labels rarely match their URLs (a "Profiles" item can
link to `/providers`), so build the label -> route map before deep-diving.

## 3. Click controls that only exist after interaction

Modals and drawers are absent from the first dump. Drive them with a ~40-line CDP script
(`node --experimental-websocket`, `fetch http://127.0.0.1:9222/json/list` for the page target,
`Runtime.evaluate` to click by exact-then-substring innerText, then dump `document.body.innerText`).
Print whether each click hit or missed — a MISS on a row means it is not a button, which is
itself the answer ("no per-row action exists").

## 4. Populate state before judging emptiness

An empty list hides every per-item control. Create one throwaway item through the tool's own
CLI (cheaper than filling a form via CDP), re-dump, and enumerate `aria-label`/`title` on the
row's icon-only buttons. Delete it afterwards.

## 5. Attribute candidate routes to implementations

Enumerate what the server can even do:

    grep -rhoE "(get|post|put|delete|patch)\(['\"][^'\"]+['\"]" <server-dir> | sort -u

Then, for every route whose name matches the feature, open its handler and follow the call.
The trap: `POST /proxy-start` existed but called `ensureCliproxyService()` — a different
daemon than the one in question. Close it with an importer check: if no file under the web
server imports the feature's module, the UI provably cannot reach it, which is stronger than
"I found no button".

## Report

State the verdict as capability + receipt pairs (route file:line, importer absence, MISS on a
click), and say which steps of the workflow still require the CLI. When a mostly-UI path is
possible via a workaround (pin the daemon's port, then register it as an ordinary endpoint),
give it, with the condition that makes it break.
