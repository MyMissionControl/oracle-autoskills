---
name: prove-azure-oneploy-landed
description: Use when a zip/OneDeploy to Azure App Service reports success and you must prove the new code is serving — Oryx compresses the output so wwwroot has no readable source, and HTTP 200 lies.
installer: auto-skill
created_at: 2026-08-03T15:03:03+07:00
created_session: 
trigger: error-recovery
created_by: claude
category: deploy
content_hash: 8bf0ce83409c32ca604177ea3b8162da7722072d7453c2d92dce5032bc19ad30
---
---
name: prove-azure-oneploy-landed
description: Use when a zip/OneDeploy to Azure App Service reports success and you must PROVE the new code is serving — Oryx compresses the output so wwwroot has no source to read, and 200 lies.
---

# Proving an Azure App Service zip deploy actually landed

`az webapp deploy` returning `"status": 4, "complete": true` means the package
was accepted. It does not mean the new code is serving. Both failure modes
below were observed on the same app in one session, each returning HTTP 200
the whole time.

## Failure mode 1: deployed but not running

The site kept serving the OLD page after a successful deploy — the previous
process was still alive. Fix: restart, then poll for a marker unique to the
new build.

```bash
az webapp restart -n "$APP" -g "$RG"
for i in $(seq 1 30); do
  c=$(curl -s -o /tmp/live.html -w '%{http_code}' --max-time 240 "$URL/")
  [ "$c" = 200 ] && grep -q "$NEW_MARKER" /tmp/live.html && break
  sleep 6
done
```

Apps with `alwaysOn: false` are the ones that need this. Check it:
`az webapp config show -n "$APP" -g "$RG" --query alwaysOn`. That setting also
causes cold-start 504s for the first visitor after idle — Basic tier and above
can enable it at no extra cost.

## Failure mode 2: verifying against a non-discriminating marker

Content-hashed asset names look like proof and are not. For a JS bundler,
framework/vendor chunk hashes depend only on dependency versions, so they are
IDENTICAL across builds — matching them proves nothing. Only a marker whose
value your change actually altered counts: a string you added, a class name
you edited, a testid you introduced.

## Reading what is really running

**Interpreted runtimes with a server-side build (Python/Node + Oryx).** When
`SCM_DO_BUILD_DURING_DEPLOYMENT=true` and the output is large, Oryx sets
`CompressDestinationDir` and `wwwroot` holds only `output.tar.zst` +
`oryx-manifest.toml` — there is no source tree to read, and
`/api/vfs/site/wwwroot/<your file>` 404s. That artifact IS what the app runs,
so download and diff it:

```bash
TOKEN=$(az account get-access-token --resource https://management.azure.com --query accessToken -o tsv)
SCM="https://$APP.scm.azurewebsites.net"
curl -s -H "Authorization: Bearer $TOKEN" "$SCM/api/vfs/site/wwwroot/" | python3 -m json.tool   # see the real layout first
curl -s -H "Authorization: Bearer $TOKEN" "$SCM/api/vfs/site/wwwroot/output.tar.zst" -o live.tar.zst
zstd -dc live.tar.zst | tar -xO ./path/in/app.py > live.py
# then sha256 live.py against `git show <sha>:path/in/app.py` — bind the proof to a commit
```

An ARM bearer token authenticates Kudu's VFS. Note Kudu's `/api/command`
(remote shell) may be blocked by policy and is not needed for this.

**Client bundles.** Fetch the served HTML, extract every asset it references,
download them, and grep for your marker. This checks what a browser actually
gets, including whether the HTML still points at stale assets:

```bash
curl -s "$URL/" -o live.html
for c in $(grep -oE '/_next/static/[A-Za-z0-9._/-]+\.js' live.html | sort -u); do
  curl -s "$URL$c" >> allchunks.js
done
grep -c "$NEW_MARKER" allchunks.js      # must be >0
grep -c "$OLD_MARKER" allchunks.js      # must be 0
```

Asserting the OLD marker is absent matters as much as finding the new one.

## Bind the verdict to a commit, and check the data

- sha256 the running file against `git show <sha>:<path>`, not against your
  working tree — the working tree can drift from what you shipped.
- Snapshot a public read endpoint before and after and diff it, so you can
  state that the deploy changed code without touching data. Ignore fields that
  legitimately vary (time-signed URLs, tokens).
- Record the previous deployment id (`az webapp log deployment list`) before
  deploying. Without slots there is no one-click rollback; rollback means
  rebuilding the previous commit and redeploying, so know exactly which commit
  prod was on.

## If a resource seems not to exist

`az resource list --name "$APP"` returning nothing means your login lacks RBAC
on its resource group, not that the app is absent — the host may well be
answering on the public internet. Confirm with `curl` before concluding
anything, and check `az account list` / the RG list for what you can actually
see. Never deploy into a similarly-named app in a different resource group.
