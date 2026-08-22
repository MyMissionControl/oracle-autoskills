---
name: multi-provider-feasibility-audit
description: 'Use when asked whether a tool that drives one vendor''s agent CLI can use another provider (switching, or mixed roles): separate the auth/protocol wall from your own routing-scope wall from runtime…'
installer: auto-skill
created_at: 2026-08-21T13:48:59+07:00
created_session: 
trigger: 'complex-task'
created_by: 'pattawub'
category: 'architecture'
content_hash: 778793988bef7bcbc904c3365bac7128d85daa4181280dd99670a2f1fcb71bcb
---
# Audit whether a single-vendor agent-driving tool can go multi-provider

Use when asked "can I plug provider B into my tool that drives vendor A's agent CLI",
or "can role X run on A while role Y runs on B". Answer by separating THREE walls that
get conflated. Never answer from the vendor's marketing page alone.

## Wall 1 — auth/protocol (outside your control)

For each candidate provider, classify the credential, not the brand:

- **consumer subscription** (chat plan) → almost always NO API surface. Only the vendor's
  own binary can spend it, in its documented headless mode. Look for the CI/automation doc
  that names the credential file the binary reads.
- **replaying that subscription's OAuth token from your own HTTP client** → check the
  vendor's *developer/legal* page for the phrase "third-party" + "route requests through
  ... plan credentials", and check for enforcement history (mass suspensions). Treat
  "nobody has been banned yet" as precedent risk, not permission.
- **"coding plan" that issues an API key** → this is the clean path: subscription pricing,
  key credential, often a base URL that speaks the incumbent's protocol so the existing
  env-var seam works unchanged.
- **cloud-gateway variants** (managed model endpoints from the big clouds) → sanctioned,
  but usually key/IAM, not subscription.

Then read the plan's **automation clause** separately from its integration page. A plan may
document "use this in <editor>" while prohibiting "automated or backend API usage" — an
orchestrator fanning out N panes is exactly what that clause targets. This is the finding
teams miss, because it lives on a different page from the setup snippet.

## Wall 2 — routing scope inside YOUR tool (cheap to fix, usually mis-diagnosed as hard)

Mixed providers need per-pane/per-process routing. Before declaring "needs new plumbing",
grep for the seams that usually already exist:

    grep -rn "new-session -e\|set-environment\|setenv" src/     # per-session env
    grep -rn "createTerminal\|spawn\|execFile\|execSync" src/    # does any pass env:?
    grep -rn -- "--settings\|--config\|CONFIG_DIR" src/          # per-launch config channel
    grep -rn "VAR=.*<binary>\|ENV_PREFIX\|LAUNCH_ENV" src/       # inline shell env prefix

Rank the candidates by **documented precedence**, not by convenience:
1. a per-launch config flag whose scope the vendor documents as outranking the user config
   file — best, because a global config write cannot silently win over it;
2. an inline `VAR=x <binary>` shell prefix — only if the vendor documents shell-env vs
   config-`env` precedence. If undocumented, do NOT build a mixed-provider design on it.
3. relocating the whole config dir per pane — usually poisons your own readback layer
   (transcript paths, status line, budget) and should be rejected on that ground.

If the global switcher deletes its managed keys before each write, it is single-slot by
construction: confirm with the writer function, and say "one provider at a time" as a
code fact, not a guess.

## Wall 3 — runtime coupling (the expensive one)

Only relevant if a *different agent CLI* must run, not just a different endpoint.
Enumerate coupling by category, each with file:line, and separate load-bearing from cosmetic:

- **state readback / transcript schema** — turn-end detection, context size, compaction
  accounting, "did the pane consume my input". Count the call sites; each needs a per-runtime
  adapter. Also find what stamps the pane→session key (often a vendor hook) — that is the
  single upstream dependency of the whole tier.
- **TUI screen-scrape vocabulary** — spinner glyphs, footer strings, capture-window depths
  tuned to one TUI's geometry. Note the asymmetric cost: a false-idle read sends keys over
  live work.
- **in-band commands** typed into the pane (slash commands, skill invocation). Flag any that
  are load-bearing rather than cosmetic (e.g. the only thing keeping a long conversation
  under the context ceiling).
- **launch flag surface**, and whether it is duplicated in more than one repo (it usually is).
- **gates that FAIL CLOSED** — a gate that parks/blocks on unknown state will permanently
  block a foreign runtime. Convert to SKIP-on-unknown BEFORE any mixed run. Find these by
  looking for the park/abort branch, not the pass branch.
- **cost/usage math** — a substring-matched rate table bills unknown model ids at the most
  expensive tier. Worse for quota-based plans: there is no per-token charge at all, so the
  dashboard invents a cost. Quota plans need a request-count model, not a rate table.
- **agent-agnostic parts** — say them out loud so nobody rewrites them: file/marker
  protocols, git/PR/worktree machinery, browser-driven checks, tmux-level send-keys.

## Verify before reporting

Adversarially verify the two load-bearing claims separately, because they fail differently:
- "provider B's subscription cannot drive the tool at all" — try hard to refute: the
  coding-plan class usually refutes the absolute form while leaving the mechanism claim intact.
- "my tool cannot run two providers at once" — refute from the code, not from a summary;
  an unused per-launch config channel is the usual counter-evidence.

## Report shape

Answer in three lines before any detail: switching-over-time = <state>, simultaneous =
<state>, different-CLI worker = <state>. Then the wall that actually blocks each, with
file:line or vendor URL. Recommend the cheapest wall first; never lead with the rewrite.

## Two corrections from a live run of this procedure

**A tool layer CAN reach another provider.** Do not repeat the tempting claim that "routing the agent's
tools through a central layer buys uniform tools, not provider reach". It is false whenever a tool in that
layer can do inference or spawn a process: a tool that shells out to another vendor's agent CLI runs a full
agent loop on that vendor's own credentials, and the answer comes back into the outer harness's context.
Check the tool layer already installed — an "call an arbitrary MCP server" tool that takes `command`/`env`
with no allowlist is provider reach *and* a sandbox hole (a denied shell tool contains nothing while such a
tool is connected). Reach is ALSO separately available as a per-process env var on the launch line, which is
usually cheaper than any of this.

**Measure the fixed harness tax before designing a stack.** If the plan is "keep the vendor harness but
forbid its tools", the tax decides it, and the intuition is wrong: on one measured harness, denying eleven
built-in tools saved 8.9% of a 48k-token-per-turn baseline, because the residual was dominated by a skills/
command catalog nobody had counted. Denial does remove a tool's schema from the request — it just removes
the wrong 9%. Probe the knobs individually (deny tools / remove tools / replace system prompt / disable the
command catalog), and watch for a knob that removes a *deferral* mechanism and inflates your own layer
instead. Note that a fresh one-shot per turn never gets the cache discount a resumed session gets, so
"per-turn shell-out" and "long-lived session" are different economies, not the same one.
