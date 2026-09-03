---
name: test-blocking-shim-grammar
description: 'Use when auditing a hand-written wrapper/blocklist shim that guards a dangerous CLI: prove which invocations get past it via an exec-neutered copy plus the tool''s own pure resolvers, without running…'
installer: auto-skill
created_at: 2026-09-03T14:45:59+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'adversary-subagent-C6'
category: 'security'
content_hash: 3938fabce40737f891483032237b0d802e43ae3baab715e9121b441d26962d6a
---
# Test a blocking wrapper's grammar without running the dangerous tool

Use when a hand-written shim/wrapper on PATH blocks some subcommands of a real tool
(`case "$1" in ...`, an argv scan) and you must prove which invocations get past it —
but actually running them would damage a live system (kill a daemon, rewrite a config dir).

## 1. Clone the shim, neuter only its final exec

The guard logic is everything ABOVE the handoff line. Replace exactly that one line so the
copy prints what it *would* have run:

    sed 's|^exec <realbin> "$@"$|echo "PASSTHROUGH -> $*"|' <shim> > /tmp/shim-copy.sh
    chmod +x /tmp/shim-copy.sh
    diff <shim> /tmp/shim-copy.sh     # MUST show exactly 1 changed line — else you tested something else

Then run the full matrix through the copy: every blocked name, every alias, every
flag-before-subcommand form, every nested form. You get a BLOCKED/PASSTHROUGH table with
zero risk. Print it as `printf '%-40s => ' "$*"` so misses are obvious.

## 2. Prove where a passed-through invocation lands, using the tool's OWN pure functions

Do not infer from reading. `node -e` into the vendored dist and call the resolver/parser
directly — these return data and never invoke handlers (handlers are usually behind a
dynamic `import()` inside `handle`, so requiring the router module is inert):

    node -e 'const {ROUTES}=require("./x/router"); const {resolve}=require("./x/named");
             for (const t of ["cmd","--cmd"]) console.log(t, resolve(t, ROUTES)?.name)'
    node -e 'const {extractOption}=require("./x/arg-extractor");
             console.log(extractOption(["--backend","original","stop"],["--backend"]).remainingArgs)'

Check the module's `require` list first: safe only if top-level requires are pure.

## 3. The three holes a name-based guard almost always has

- **Aliases.** A router that matches `route.name === t || route.aliases?.includes(t)` accepts
  `--cmd` for `cmd`. Guarding the bare name leaves the alias open. Dump the whole alias table
  and diff it against the blocklist — do not spot-check.
- **Flag-before-subcommand.** If the tool parses/extracts option flags BEFORE reading
  `args[0]` as the subcommand, then `tool group --opt value blocked-sub` slips past a guard
  that tests `"$2"`. Confirm the extractor splices flag+value (`splice(i,2)`), and test the
  `--opt=value` form too (`splice(i,1)`) — different code path, same hole.
- **Siblings that reach the same primitive.** Blocking `stop` is pointless if `restart`,
  `--install`, an auto-repair `--fix`, a web dashboard route, or the normal run path all call
  the same kill/write function. Enumerate callers of the PRIMITIVE, not of the command:
  `grep -rn "killFn(" --include=*.js . | grep -vE "function killFn|exports\.killFn"`

## 4. Report reachability separately from mechanism

"Code path X reaches the kill" and "invocation Y gets past the guard" are different claims.
An audit that names a blocked command as a bypass is wrong even when its mechanism analysis
is right. Settle reachability with the §1 matrix, mechanism with §2–3, and say which is which.

## Gotchas

- Verify the shim is what PATH actually resolves (`type -a <cmd>`); a second install elsewhere
  makes the whole audit moot.
- A guard loop `for a in "$@"` is position-independent and usually NOT bypassable by reordering —
  test it rather than assuming it has the same hole as the `case "$2"` check.
- Grep with alternation may be rewritten by a shell hook into a tool with different regex rules;
  if `\|` errors or returns 0 matches, re-run with `grep -E` or the proxy escape hatch.
