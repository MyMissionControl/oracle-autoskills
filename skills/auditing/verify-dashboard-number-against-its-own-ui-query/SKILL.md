---
name: verify-dashboard-number-against-its-own-ui-query
description: 'Use when a local dashboard''s usage/cost total is disputed: recover the UI''s default query params from the shipped bundle before comparing, then ground-truth with the upstream library the tool…'
installer: auto-skill
created_at: 2026-09-04T18:41:45+07:00
created_session: 
trigger: 'complex-task'
created_by: 'subagent:ccs-usage-audit'
category: 'auditing'
content_hash: 5902d1355741d2b34dc44674c06fc9c945752c9e961f9cb415a4faccbeff25b0
---
# Verify a dashboard number against the query its own UI sends

Use when someone disputes a number on a locally-served dashboard ("the usage/cost total is
wrong") and you are about to compare an API endpoint against your own re-scan. Comparing the
*unfiltered* endpoint is the classic wasted audit: the page almost never asks for that.

## 1. Recover the page's DEFAULT query from the shipped bundle (do this first)

The endpoint you can curl and the request the page makes are different things.

```bash
ASSETS=<install>/dist/ui/assets            # or wherever the SPA ships
grep -l "<api-path-fragment>" $ASSETS/*.js  # e.g. "usage/summary" — NOT "/api/usage" (built at runtime)
python3 - <<'EOF'                           # make the minified chunk readable
import re; s=open('<chunk>.js',encoding='utf8',errors='replace').read()
print(re.sub(r'([;{}])', r'\1\n', s)[:20000])
EOF
```

Look for: the `URLSearchParams` builders (which params exist at all), and the page component's
initial state — `useState({from: B(new Date,30), to: new Date})`. Resolve minified helpers
through the export map of the imported chunk (`export{zr as K,...}` then read `function zr`) —
`subDays(now,30)` means **the default view is a 30-day window, not all time**.

Also check for per-viewer persistence (`localStorage.getItem('<app>.<setting>')`); read the real
browser store rather than guessing:

```bash
python3 -c "
import glob
for p in glob.glob('<HOME>/.config/chromium/*/Local Storage/leveldb/*'):
    b=open(p,'rb').read()
    if b'<storage-key>' in b: print('HIT',p)"
```

## 2. Then curl the endpoint BOTH ways and quote both

```bash
curl -s "http://127.0.0.1:<port>/<api>/summary"                      # what auditors compare
curl -s "http://127.0.0.1:<port>/<api>/summary?since=$(date -d '30 days ago' +%Y%m%d)&until=$(date +%Y%m%d)"
```
If they differ materially, every earlier claim was measured against a number nobody sees.

Check the **timezone seam** while you are here: a UI that builds date params from local
`getFullYear/getMonth/getDate` while the server buckets on `timestamp.slice(0,10)` (UTC) has
window edges off by the UTC offset. Read `date; date -u` on the box.

## 3. Ground-truth with the upstream library the tool says it replaced

Vendored parsers often carry a header like "Replaces <lib> dependency with optimized custom
implementation". That library IS your oracle — run it on the same corpus:

```bash
cd /tmp/ref && NPM_CONFIG_CACHE=/tmp/ref/cache npm pack <lib>@<ver> && tar xzf <lib>-<ver>.tgz
grep -rho "GLOB_PATTERN\s*=\s*[^;,)]*" package/dist | sort -u      # recursive "**/*.jsonl"?
grep -rn "uniqueHash\|processedHashes" package/dist | head          # dedup key?
node package/dist/index.js <report> --json --since ... --until ... > out.json   # its own total
```
Two independent implementations agreeing (yours + the library's) is far stronger evidence than
either alone. Expect the parse to take many minutes on a GB-scale corpus — run it with
`run_in_background: true` and poll with an `until [ -s out.json ]` loop (chained `sleep`s are
blocked).

## 4. Separate "package defect" from "our install" from "our workload"

- **our install?** `npm ls --depth=0` (missing/invalid markers), every asset referenced by
  `index.html` exists, no zero-length files, and check what `--ignore-scripts` actually skipped
  (read `scripts/postinstall.js` — usually only config seeding). Native deps with a `prebuilds/`
  dir need no build step. A file declared in `package.json` `files[]` but absent may be missing
  from the **upstream tarball** too — verify with `tar tzf` before blaming the install.
- **our config?** Read the scanner's options object and grep the module tree for `process.env.*`.
  If no flag exists that would change the behaviour, no configuration choice can be the cause.
- **our pin?** `npm pack` two or three older versions and grep the same code path. Same defect in
  every version = not the pin.
- **our workload?** Classify the missed/extra records by shape and report the share. "99% of the
  gap comes from <feature X>" tells the user whether the defect bites everyone or only them.
