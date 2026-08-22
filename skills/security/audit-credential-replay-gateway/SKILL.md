---
name: audit-credential-replay-gateway
description: 'Use when judging whether a local gateway/proxy may spend a paid AI subscription in another harness: classify token-replay vs client-identity spoofing from its shipped bundle, mine its own…'
installer: auto-skill
created_at: 2026-08-21T16:27:19+07:00
created_session: 
trigger: 'complex-task'
created_by: 'subagent-research'
category: 'security'
content_hash: 97fb5675e06bb0e53ec6200cc7d21c6ed26ec1a811ce213976645eed974f3975
---
# Audit a credential-replay gateway before routing a subscription through it

Use when deciding whether a local gateway/proxy (or any "use your <vendor> plan in
another harness" tool) is safe and permitted to spend a paid subscription. Its README
is marketing; the answer is in its build output and in the vendor's own clause page.

## 1. Read the tool's shipped bundle, not its docs

Install/vendor it CAGED (fake HOME) and never on PATH. Then:

```bash
P=<pkg-root>
ls $P/config/            # per-provider presets: what BASE_URL is the harness pointed at?
cat $P/config/base-<prov>.settings.json
ls $P/dist/              # per-vendor dirs = per-vendor client code
```

A preset pointing the harness at `http://127.0.0.1:<port>/api/provider/<vendor>` means
the tool replays the credential in *its own* HTTP client. That is categorically
different from shelling out to the vendor's own binary — and it is the pattern vendors
detect and block.

## 2. Classify each provider: own-binary vs token-replay vs identity-spoof

```bash
cd $P/dist/<vendor>
grep -rhoE "https://[a-zA-Z0-9._/-]+" *.js | sort -u        # real upstream hosts
grep -n "spawn\|execFile\|npx " *executor*.js               # does it run a real CLI?
grep -oiE "'x-[a-z0-9-]+'|user-agent|CLIENT_VERSION|checksum" *.js | sort -u
```

Escalating severity:
- spawns the vendor's own CLI  → weakest claim of violation
- replays the OAuth token in own client → breaches most "only via our interfaces" clauses
- **forges client identity** — pinned `CLIENT_VERSION`, `x-<vendor>-client-type: ide`,
  a reimplemented anti-abuse `checksum(machineId)`, hand-rolled protobuf for a private
  endpoint → reverse-engineering + circumventing protective measures. Highest risk.

## 3. Let the tool's own safety code rank the vendors for you

A gateway that has been burned ships ban machinery. Find it:

```bash
grep -rn -o ".\{0,140\}account ban.\{0,200\}" --include=*.js $P/dist | head
grep -rn "BAN_WARNING_PROVIDERS\|BAN_PATTERNS" -A6 $P/dist
```

`BAN_WARNING_PROVIDERS` / ban-string lists / a dashboard consent checkbox are the
maintainers' own admission of which subscriptions get accounts killed, and the issue
number they cite is the incident log. This is stronger evidence than any blog post.
Note the asymmetry: warnings often live only in code, not in the README or docs site.

## 4. Get the vendor clause from the right page

The clause is frequently NOT in the consumer Terms of Service, even when press
reports say "they updated their ToS". Check, in order:
- the product's **docs** usage-policy / legal-and-compliance page (often the real text)
- product-specific terms
- the **enforcement notice text** users post in the vendor's community forum — this is
  the operative list of banned behaviours, and often names "proxy usage" explicitly
- the vendor's own auth doc: an *enumerated list of supported clients* that contains
  only first-party clients is silence, not permission

Verify by asking for verbatim headings; if a fetch reports the section absent, believe
it over the secondary reporting, and say so.

## 5. Verdict in four buckets — never round silence up

`WORKS-AND-PERMITTED` / `WORKS-BUT-PROHIBITED` / `TECHNICALLY-BLOCKED` / `UNKNOWN`.

"No enforcement yet" is **UNKNOWN**, not permitted. Only an affirmative vendor clause
blessing third-party credential use earns PERMITTED. A vendor engineer declining to
confirm permissibility is evidence *against* PERMITTED. Record for each verdict: the
mechanism tier from step 2, the clause URL, and the enforcement date if any.
