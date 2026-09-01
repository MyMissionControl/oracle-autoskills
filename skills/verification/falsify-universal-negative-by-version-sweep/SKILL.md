---
name: falsify-universal-negative-by-version-sweep
description: 'Use when refuting a ''tool never does X / on every version'' claim backed by a few recent versions: sweep the full published version range oldest-first, prove the counterexample behaves, close…'
installer: auto-skill
created_at: 2026-09-01T18:27:42+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'verifier-subagent'
category: 'verification'
content_hash: 397a94514e221481b1eefa00f724b65b6d8a2569ad4b730ab85a68634fa1bbf2
---
# Falsify a universal-negative tool claim by sweeping the FULL published version range

Use when someone asserts a tool "never does X" / "on every version" / "always installs only
A,B,C", and backs it with a handful of recent versions. A contiguous modern band is the weakest
possible evidence for a universal negative: behaviour changes cluster in the tool's first months,
long before the band anyone still runs.

## Steps

1. **Reproduce their exact command first.** If it does not reproduce, stop — that is the finding.
2. **Get the real version list, do not guess it:**
   `npm view <pkg> versions --json` (or `pip index versions`, `gh release list -L 200`).
   Print `len()` and the first ~12 entries. The claimant almost never went near index 0.
3. **Sweep the EARLIEST versions, not more recent ones.** Their band is already covered.
   Run oldest-first with a per-run timeout and a fresh output dir:
   ```
   for V in <first 8 published>; do rm -rf "d-$V"; mkdir -p "d-$V"
     out=$(timeout 180 npx --yes <pkg>@$V <cmd> --output-dir "$PWD/d-$V" 2>&1); rc=$?
     printf '%-8s rc=%-3s -> [%s]\n' "$V" "$rc" "$(ls d-$V | tr '\n' ' ')"
   done
   ```
   Read rc AND the artifact list. `rc=0` with an EMPTY dir is its own answer (flag not yet
   supported) — not a pass.
4. **Do not stop at "a file appeared".** Prove the counterexample *behaves* like the thing being
   denied: put the old artifact on PATH and run the real scenario. A shim that merely exists but
   dies with `Cannot find module` is still a counterexample, but a *different* one — say which.
5. **Run the positive control.** Force the mechanism explicitly (`<cmd> <the-excluded-name>`) and
   capture the exact error string. Without it you cannot tell "absent" from "present but silent".
6. **Close every inference they left open.** If they only tested the flagged form
   (`--install-directory`, `--prefix`, `--target`), test the DEFAULT form too — defaults often
   take a different code path. Build a fake dir containing a wrapper named like the tool, put it
   first on PATH, run bare.
7. **Date the counterexample** (`npm view <pkg> time --json`) and check whether any bundling
   distribution ever shipped it. This is what separates "the wording is wrong" from "the
   conclusion is wrong" — report both verdicts separately.

## Reporting

- Universal quantifier false + operational conclusion intact = **partly wrong**, not "confirmed".
  Rewrite the claim with the real version floor ("from X onward") instead of "never".
- Say explicitly which half you could not verify (e.g. "no distro ever bundled it" reasoned from
  publish dates, not from opening a distro tarball) and label it NOT VERIFIED.

## Traps

- A hook may rewrite `rg`/`grep`/`find` and mangle line-numbered output. Read source with
  `python3` + explicit line indexing when line numbers are load-bearing.
- Verify the cited line is in the function they think it is: the same ternary often appears in
  both the `enable` and `disable` (or `add`/`remove`) command bodies.
- Old versions installing to a DEFAULT directory can clobber your live toolchain. Always pass an
  explicit output dir, and re-`ls` your real bin dir afterwards to prove nothing was overwritten.
