---
name: verify-deploy-landed
description: Use when a deploy reports success but you must prove the NEW build is serving. HTTP 200 lies; byte-compare a content-hashed asset + read the platform deployment record.
installer: auto-skill
created_at: 2026-07-28T07:08:59+00:00
created_session: 
trigger: error-recovery
created_by: claude-opus-5
category: deployment
content_hash: 9d2c7ab873b37958cbaf40a01af6b3161d42c293ea6fa93ec7bd06354fb0ff22
---
---
name: verify-deploy-landed
description: Use when you deploy a built web app and need to prove the NEW build is actually serving — HTTP 200 and a "success" status both lie. Byte-compare a content-hashed asset and read the platform's own deployment record.
---

# Prove a deploy actually landed

A deploy can report success while the old build keeps serving, and the old
container answers 200 on every page the whole time. Two checks that cannot
be faked, neither of which needs shell access to the host.

## 1. The platform's deployment record

Ask the control plane which deployment is *active*, not whether the deploy
command exited 0:

```bash
# Azure App Service
ID=$(az webapp show -g <rg> -n <app> --query id -o tsv)
az rest --method get --url "https://management.azure.com$ID/deployments?api-version=2023-12-01" \
  | python3 -c "import sys,json;[print('active' if r['properties'].get('active') else '      ',
      r['properties'].get('received_time','')[:19], r['properties'].get('status')) for r in
      sorted(json.load(sys.stdin)['value'], key=lambda x: x['properties'].get('received_time',''))]"
```

An `active: true` row whose `received_time` is your deploy is real evidence.
`numberOfInstancesSuccessful` in the deploy command's own output is not — it
describes the request, not what the running process loaded.

## 2. Byte-compare a content-hashed asset

Modern bundlers put a content hash in asset filenames. That makes the served
file self-verifying: if the old build were live, the new hash would 404.

```bash
# Next.js example: find the chunk for the page you changed, fetch it, sha256 both
python3 - <<'PY'
import json, hashlib, os, urllib.request
m = json.load(open('.next/app-build-manifest.json'))
key = [k for k in m['pages'] if '<your/page>' in k][0]
for f in [x for x in m['pages'][key] if x.endswith('.js') and '/app/' in x]:
    local = os.path.join('.next', f)
    lh = hashlib.sha256(open(local,'rb').read()).hexdigest()
    with urllib.request.urlopen('https://<host>/_next/' + f, timeout=60) as r:
        rh = hashlib.sha256(r.read()).hexdigest()
    print(f, r.status, 'IDENTICAL' if lh == rh else 'DIFFERENT')
PY
```

Pick an asset belonging to the code you changed, so its hash actually moved
between builds. A 404 means the old bundle is still being served.

## Fallbacks when the admin API is locked down

Managed environments often disable basic-auth publishing, so file-browsing
endpoints (Kudu `/api/vfs/...`, `/api/command`) return **401**. An empty body
from such a check is the CHECK failing, not a statement about the deployment —
never report it as "still the old build". Fall back to (1) and (2), both of
which use the normal control-plane and public HTTP paths.

## "Landed" is not "correct"

Both checks above prove the new artifact is serving. Neither says the
artifact is *right* — a broken build deploys just as successfully as a good
one. When the framework inlines configuration at BUILD time (anything
`NEXT_PUBLIC_*`, `VITE_*`, `REACT_APP_*`), values held in the host's runtime
settings never reach the browser bundle, and building without them exported
silently bakes in the dev fallback. The deploy then works perfectly and every
API call in the browser goes to `localhost`.

So assert on bundle CONTENT before shipping, and fail closed:

```bash
BAD=$(grep -rl "localhost:8000" dist/assets 2>/dev/null | wc -l)   # dev fallback
GOOD=$(grep -rl "your-real-api-host" dist/assets 2>/dev/null | wc -l)
[ "$BAD" = "0" ] && [ "$GOOD" != "0" ] || { echo "ABORT: wrong build, not deploying"; exit 1; }
```

Repeat the same grep against the *served* assets afterwards. Then commit the
production values into a build-time env file (`.env.production` and friends)
so the correct build stops depending on anyone remembering to export them —
these values ship to browsers anyway, so they are not secrets.

Finish by exercising the actual path the user reported: a real request from
the real origin (preflight + one POST), confirming you get an application
error rather than a network failure.

## Never filter the deploy command's own output

Capture it whole; read it after. A pipe like `| grep '"status"'` throws away
exactly the line that explains a failure — an auth error, an expired
credential, a missing file — and leaves a log that looks merely *empty*, which
reads as "fine" at a glance. If a deploy's status line is absent from your log,
treat that as FAILED until proven otherwise, and re-run unfiltered.

Same for the exit code: some CLIs print `ERROR:` and still exit 0 inside a
`{ ... } > log` block, so neither the code nor a silent log is evidence.

## Packaging pitfall

Build the artifact and deploy it in ONE command. A gap between packaging and
deploying (especially one spanning a question to your human partner) lets a
temp-dir cleaner delete the artifact, and the deploy fails with a confusing
"not a valid local file path" — pointing at a file you just listed.
