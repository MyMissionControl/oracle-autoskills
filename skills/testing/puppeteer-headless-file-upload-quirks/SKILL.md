---
name: puppeteer-headless-file-upload-quirks
description: 'Debug puppeteer/headless-chromium file-input upload failures during live-verify: snap confinement misleads as a network error, webkitdirectory CDP no-ops'
installer: auto-skill
created_at: 2026-08-09T19:47:13+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'jack'
category: 'testing'
content_hash: c2c65f7b6ff9830ab4c26fdc8dc2795e6170f8e75bb4bcbe5896b22342dbb985
---
---
name: puppeteer-headless-file-upload-quirks
description: Debug Puppeteer/headless-Chromium file-input upload flows that fail mysteriously (misleading network errors, empty file lists) when live-verifying an upload feature end-to-end
---

# Puppeteer + headless Chromium file-input upload quirks

Use when live-verifying an "upload a file/folder" feature through a real
headless browser (not just unit tests) and the upload silently fails or
throws a network-looking error that makes no sense for a `localhost` request.

## Symptom 1: misleading network error from a snap-packaged Chromium

If `which chromium` resolves into `/snap/bin/chromium` (or a wrapper like
`/usr/bin/chromium-browser` that execs the snap binary), files staged under a
deep/unusual temp path (e.g. an agent sandbox's scratch directory under
`/tmp/...`) can be *selected* into an `<input type="file">` successfully —
`input.files[i].name` and `.size` look correct — but fail when the browser
actually reads the bytes to serialize the multipart body. The failure does
**not** surface as a permissions error. It shows up as something like:

- `net::ERR_ALPN_NEGOTIATION_FAILED` on the request (nonsensical for a plain
  `http://` request — no TLS/ALPN should even be involved)
- `TypeError: Failed to fetch` in the page

`--no-sandbox` does **not** fix this — that flag only disables Chromium's own
renderer sandbox, not the outer snap/AppArmor confinement that blocks the
file read.

**Fix**: stage any file the browser needs to upload under `$HOME` (e.g.
inside the project/worktree being tested), never under an arbitrary `/tmp`
subtree, whenever the target Chromium is a snap install. Confirm the binary
with `which chromium; snap list chromium` before assuming this is your bug.

**Isolate it fast**: reproduce with a minimal `page.evaluate(() => fetch(...))`
using an in-page `new Blob([...])` (always works, no disk read) vs. a real
`File` obtained via `elementHandle.uploadFile(path)` (fails if this is the
cause) — same origin, same endpoint. If the Blob version works and the real
File version fails with a network-flavored error, this is almost certainly
the snap-confinement file-read issue, not a server or app bug.

## Symptom 2: `webkitdirectory` input silently ignores `uploadFile()`

Chromium's CDP command `DOM.setFileInputFiles` (what
`elementHandle.uploadFile(...)` uses under the hood) no-ops on `<input
type="file" webkitdirectory>` — after calling it, `input.files.length` is
still `0`, with no thrown error.

**Fix for test automation only** (does not affect real users, who pick a
folder through the native OS dialog which Puppeteer can't drive here anyway):
strip the attribute immediately before injecting files, since the app code
only reads `.files` / `.webkitRelativePath` afterward and doesn't care how
the attribute got removed:

```js
const input = await page.$('input[type="file"]');
await page.evaluate((el) => el.removeAttribute('webkitdirectory'), input);
await input.uploadFile(path1, path2, ...);
```

Because `webkitRelativePath` is empty for files injected this way (it's only
populated by a real native directory picker), any client-side "does this
selection contain file X" check should fall back to `file.name` when
`webkitRelativePath` is empty, e.g.:
`(file.webkitRelativePath || file.name).split('/').pop() === 'X'`.

## General diagnostic order for a submit-does-nothing form during live-verify

1. Print `input.files.length` and `form.checkValidity()` via `page.evaluate`
   right before clicking submit — most "click resolved but nothing happened"
   cases are native HTML5 constraint validation silently blocking the submit
   event before your JS `onSubmit` ever runs.
2. Attach `page.on('request', ...)`, `page.on('requestfailed', ...)`,
   `page.on('console', ...)`, and `page.on('pageerror', ...)` before doing
   anything else — they tell you whether the request fired at all, which
   narrows "client validation blocked it" vs. "request fired and failed" vs.
   "request succeeded but the UI didn't update" (a state-refresh bug in the
   app, not a browser-automation problem).

## Keeping the repo clean during this kind of manual verification

If the project doesn't already have a browser-automation dependency, install
one for the session only: `npm install --no-save puppeteer-core` (paired
with `executablePath` pointing at the system Chromium, so it doesn't try to
download its own). This leaves `package.json`/lockfile untouched. Delete any
throwaway verify scripts/fixtures and `npm uninstall puppeteer-core` before
the final commit so the diff stays exactly the feature work.
