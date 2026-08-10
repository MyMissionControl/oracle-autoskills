---
name: bisect-slow-dependency-install
description: 'Use when npm/pnpm/yarn install is slow: --offline and --ignore-scripts as controls, npm rebuild to pin the package, prebuilt-binary ABI check, prove the runtime fix.'
installer: auto-skill
created_at: 2026-08-10T13:10:09+07:00
created_session: 
trigger: 'complex-task'
created_by: 'claude'
category: 'build'
content_hash: 8e98ac95a34f8e3722216dd02679d1dbfa6498e60506151ebecb4d2e2f509490
---
# Bisect a slow dependency install

Use when `npm|pnpm|yarn install` (or an agent-built project's setup step) takes
minutes and someone is about to "fix" it by warming a cache or adding a registry
mirror. The bottleneck is usually **not** the network. Four commands tell you
where the time actually goes, and each one is a control that can refute the
obvious lever before you spend work on it.

## The controls, in order

Copy `package.json` + the lockfile into a throwaway dir first — never bisect in
the real project, the runs are destructive to `node_modules`.

```sh
cd <scratch>; cp <proj>/package.json <proj>/package-lock.json .
run(){ rm -rf node_modules; s=$(date +%s.%N); eval "$2" >/dev/null 2>&1; e=$(date +%s.%N); printf '%-40s %7.1fs\n' "$1" "$(echo "$e-$s"|bc)"; }

run "default"        "npm ci"
run "offline"        "npm ci --offline --no-audit --no-fund"   # control 1
run "extract only"   "npm ci --ignore-scripts --offline"        # control 2
```

1. **`--offline` ~= default -> network and registry cache are NOT the bottleneck.**
   This kills "warm the cache", "prefer-offline", "use a mirror" in one run.
   Measured case: 170.9 s offline vs 165.1 s default, with a 13 GB warm cache.
2. **`--ignore-scripts` fast, full install slow -> the time is in lifecycle
   scripts, not in downloading or extracting.** Measured case: 20.4 s vs 165 s,
   so 88% of the install was postinstall.

Then pin the single culprit — do not guess from package names:

```sh
npm ci --ignore-scripts --offline            # populate the tree once
python3 - <<'PY'                              # list packages that HAVE install scripts
import json,glob
for p in glob.glob('node_modules/**/package.json',recursive=True):
    try: d=json.load(open(p))
    except: continue
    s={k:v for k,v in (d.get('scripts') or {}).items() if k in ('preinstall','install','postinstall')}
    if s: print(d.get('name'), d.get('version'), s)
PY
for p in <the candidates>; do s=$(date +%s.%N); npm rebuild "$p" >/dev/null 2>&1; \
  e=$(date +%s.%N); printf '%-22s %7.1fs\n' "$p" "$(echo "$e-$s"|bc)"; done
```

One package normally owns almost all of it. Measured case: `better-sqlite3`
142.6 s of a 165 s install; every other script package was 1-2 s.

## Native modules: it is an ABI mismatch, not "compiling is just slow"

A native package ships prebuilt binaries per Node ABI and only falls back to
compiling when none matches. Check the runtime, then check what actually exists:

```sh
node -p "'node '+process.version+' ABI '+process.versions.modules"
cd node_modules/<pkg> && npx --no-install prebuild-install -d      # prints the miss
# and list what the project publishes, without cloning:
curl -s https://api.github.com/repos/<owner>/<repo>/releases/tags/v<version> \
 | python3 -c "import json,sys;print(sorted(a['name'] for a in json.load(sys.stdin)['assets'] if 'linux-x64' in a['name']))"
```

`prebuild-install warn install No prebuilt binaries found (target=...)` is the
whole diagnosis. Compare the asset list's `node-vNNN` values against your
`process.versions.modules`: a package can require Node >= 20 while publishing
prebuilds only for 22/24+, so a supported runtime still compiles from source on
every install, in every worktree.

**Prove the fix before recommending it.** Install the candidate runtime
side-by-side and re-run in the scratch dir, WITHOUT changing the machine default:

```sh
. "$HOME/.nvm/nvm.sh"; nvm install <major>    # does not touch `default`
node -p "process.versions.modules"; rm -rf node_modules; time npm ci
cat ~/.nvm/alias/default                       # confirm default is untouched
```

Measured case: 165.1 s -> 24.6 s, 6.7x, from the runtime bump alone.

## Reporting it inside an agent workflow

If the question was "does install cost us tokens or time", answer both and keep
them separate — they land very differently:

- **Tokens: usually near zero.** A successful install prints a few hundred
  characters. Its accumulated context cost was 0.16% of the build's input tokens.
  What is NOT near zero is that each install is a **turn**, and every turn
  re-sends the whole context: install turns were 2.4% of requests and ~2.5% of
  tokens. So truncating the install output buys nothing; removing turns does.
- **Time: report against ACTIVE wall clock, not session span.** Sessions sit idle
  for hours. Sum consecutive-record gaps capped at 60-600 s and show the share is
  stable across caps (measured 4.4% -> 2.9% across that range) — an uncapped span
  denominator understated it by 30x.
- Backgrounding an install (`nohup ... &` plus a poll loop) converts 1 turn into
  3-5. Those poll turns cost as much as the installs themselves. Make the install
  fast instead of hiding it behind polling.

## Clean up and prove you did

The scratch tree is ~1 GB. `rm -rf` it, re-check `df -h`, and confirm the real
project is untouched (`git status --porcelain` in it) before reporting.
