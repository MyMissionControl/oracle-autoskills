---
name: verify-vendored-install-command-rebuilds
description: 'Use when an audit classifies a vendored dependency as rebuildable by a command: prove it on a fresh HOME with a nonexistent prefix, tarball-integrity diff against the live tree, and the two…'
installer: auto-skill
created_at: 2026-09-03T16:24:36+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'subagent:classification-attack'
category: 'bring-up'
content_hash: 2fe4c3dd303624ae89d9e69aed4625b3b219d51ef30b6eec9e8541229637fcd7
---
# Verify a vendored install command really rebuilds its artifact

Use when a bring-up/DR audit classifies a vendored dependency as "a command rebuilds it"
(`npm i <pkg>@<ver> --prefix <dir>`, `pip install --target`, `go install`, a vendor script).
An idempotent updater that only refreshes an EXISTING tree is the classic false COMMAND.
Prove it on a machine where the artifact does not exist.

## 1. Is the source still reachable and pinned?
```
npm view <pkg>@<ver> version dist.tarball dist.integrity     # unpublished/yanked => COMMAND is dead
```
Record the integrity string. A version that resolves today is not evidence it is pinned:
check whether the on-disk manifest holds a RANGE (`^8.9.0`) while only the command string
holds the pin. If the lockfile lives only on this machine (in no repo), `npm ci` is not
available on a fresh box => exact reproduction is a today-fact, not a guarantee. Say so.

## 2. Is the live tree pristine, or hand-patched?
```
curl -sSL -o pkg.tgz <dist.tarball>
openssl dgst -sha512 -binary pkg.tgz | openssl base64 -A    # must equal dist.integrity
tar xzf pkg.tgz -C x && diff -rq x/package <live install dir>
```
`diff -rq` clean + equal `find -type f | wc -l` => pristine. Any diff => the working setup
depends on a local patch nothing rebuilds => downgrade to MANUAL.

## 3. Run the command on a fresh machine, not on this one
```
export HOME=<scratch>/freshhome; rm -rf "$HOME"; mkdir -p "$HOME"
cd "$HOME" && <the exact command, prefix inside $HOME>
```
Fake HOME does three jobs at once: proves the prefix dir is CREATED (not assumed),
gives a cold cache like a new box, and contains any install-time writes to dotfile dirs.
Then assert the EXACT path the consumer resolves, plus its MODE:
```
stat -c '%a %n' "$HOME/<...>/<entry file>"    # compare against the live one
ls -la "$HOME"                                # what did the install touch in home?
```
Diff the fresh tree against the live one (`diff -rq`, top-level dep list, lockfile key set).

## 4. `--ignore-scripts` has two independent victims — check both
- **The package's own lifecycle scripts.** Dump the FULL scripts map; `head` truncates and
  `postinstall` is often last: `node -e "console.log(JSON.stringify(require('./package.json').scripts,null,1))"`.
  Read the skipped script. If it seeds a state dir the audit's "blocks" chain hangs on,
  that state dir is a SEPARATE artifact and cannot inherit "the installer recreates it".
- **Native transitive deps.** A dep with `"install": "node-gyp-build"` / node-pre-gyp is the
  classic silent breakage. It survives only if it ships `prebuilds/<os>-<arch>/` and resolves
  at require time. Do not reason about it — load it:
```
node -e "const b=require('<fresh nm>/bcrypt'); console.log(b.hashSync('x',4).length)"
node -e "const r=require('module').createRequire('<fresh nm>/<pkg>/package.json');
  for (const d of Object.keys(require('<fresh nm>/<pkg>/package.json').dependencies))
    try{r.resolve(d)}catch(e){console.log('MISSING',d)}"
```

## 5. Is the command string itself REPO or MANUAL?
The command only counts as rebuildable if its text survives the machine:
```
git ls-files --error-unmatch <file>; git status --porcelain <file>; git branch -r --contains HEAD
```
Tracked + clean + contained in the remote branch. Then grep for a caller — a constant nothing
reads is documentation, not a rebuild path. Re-grep the line number; cited line numbers drift
and drift is not a refutation.

## Verdict shape
COMMAND survives only with: source still published, fresh-prefix run RC=0, exact entry path +
mode, tree byte-identical to live, all deps load, and the command text tracked in a repo.
Report every link of the chain the command does NOT rebuild as its own artifact.
