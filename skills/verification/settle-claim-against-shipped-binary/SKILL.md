---
name: settle-claim-against-shipped-binary
description: 'Use when proving how an installed app handles an input artifact, instead of porting its source: check the product is installed, match minified-bundle constants to public source, run the real product…'
installer: auto-skill
created_at: 2026-08-31T10:29:01+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'adversarial-verifier'
category: 'verification'
content_hash: d91cab99e72806a8e7be4958294fde890cf55b83873c9cdeb91fbc3d5714bb69
---
# Settle a "how does app X handle this artifact?" claim against the SHIPPED binary

Use when someone claims/needs to prove how an installed desktop app (VS Code, Electron app,
packaged CLI) processes an input artifact, and the tempting shortcut is to read the app's
source on GitHub and hand-port its logic into a script. A port proves what the source says,
not what the product does. Do this instead.

## 0. Before porting anything: check whether the real product is installed
    which <app> <app>-insiders <alt-name>
    ls -d ~/.<app> ~/.<app>-server
Snap/flatpak installs hide behind /snap/bin. If it is there, the port is unnecessary —
skip to step 3. (Repeated failure mode: an agent writes a 200-line port and files
"I deliberately did not run the real product" as a caveat, while the product sat in PATH.)

## 1. Get the public source at the versions that matter
    for T in main <tag-you-run> <old-tag>; do
      curl -sfL -o src.$T.ts "https://raw.githubusercontent.com/<org>/<repo>/$T/<path>" \
        && echo "$T lines=$(wc -l < src.$T.ts) hits=$(grep -ci <feature> src.$T.ts)"
    done
Do NOT assume main matches the tags — line counts drift; re-derive per ref.

## 2. Prove the SHIPPED bundle matches that source (bundles are minified, names are mangled)
Anchor on **numeric constants and string literals**, which survive minification while
identifiers do not. Pick 2+ rare numbers from the source (mode masks, magic ints, error codes):
    cd <app-install>/resources/app/out
    python3 - <<'EOF'
    import os
    for root,d,fs in os.walk('.'):
        for f in fs:
            if not f.endswith('.js'): continue
            p=os.path.join(root,f); s=open(p,errors='ignore').read()
            if '<CONST_A>' in s and '<CONST_B>' in s: print('CANDIDATE',p,len(s))
    EOF
Then print context around the hit and confirm it is the real function, not a coincidence
(a UTF-8 encoder shares mask constants with file-mode code — verify the surrounding
expression, not just the number). Repeat for EVERY entrypoint that can perform the action
(CLI process, shared/background process, main) — they are separate bundles and you must
show all of them carry the same logic before saying "the app does X".

## 3. Run the real product on a minimal fixture
Build the smallest valid artifact in a scratch dir, make the disputed property
byte-identical to production (same link target, same bytes, same length), then:
    <app> --install-extension|--open|--import <fixture>   2>&1 | cat
Snap-wrapped CLIs discard stdout to a redirected FILE but keep it through a PIPE —
always `| cat`, never `> out.txt`.
Inspect the RESULT with python os.lstat, not `ls` (a hook may rewrite ls/find/grep):
    python3 -c "import os,stat;st=os.lstat(P);print(stat.S_ISLNK(st.st_mode),oct(st.st_mode),st.st_size)"

## 4. Separate "the app accepted it" from "it works"
An install/import reporting SUCCESS is not evidence the artifact is usable. Drive the
artifact the way the app will at runtime (require/load/open it) and capture the real error.
Silent-accept-then-fail-at-use is the common shape.

## 5. Clean up product state you created
    <app> --uninstall-extension <id>
Leftover dirs and index/marker files (e.g. `.obsolete`) can survive an uninstall — remove
your own residue and re-check with `ls -d`.

## 6. Check the consumer's real input set before recommending a fix
If the fix is "remove the offending item", first run the packaging/collection command the
tool itself uses (read it from the tool's source, e.g. `npm list --production --parseable`)
and test each returned path for the bad property. The offending set is usually far smaller
than the on-disk set, which collapses a multi-step fix into one line.

## Guardrails
- Read-only targets: take md5 of any file you might touch BEFORE, diff AFTER.
- Every count re-derived with python3, never with hook-rewritten grep/find/ls.
