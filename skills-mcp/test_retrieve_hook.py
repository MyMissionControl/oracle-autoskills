#!/usr/bin/env python3
"""Tests for retrieve-hook.py — the UserPromptSubmit path that actually runs
RETRIEVE. Drives the hook as a real subprocess with a real stdin payload, the
same way Claude Code invokes it."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "retrieve-hook.py")

PASS = 0
FAIL = 0


def check(label, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS  {label}")
    else:
        FAIL += 1
        print(f"FAIL  {label}")


def fixture(root):
    def skill(name, desc, body="Body.\n"):
        d = os.path.join(root, name)
        os.makedirs(d)
        with open(os.path.join(d, "SKILL.md"), "w") as f:
            f.write(f"---\nname: {name}\ndescription: {desc}\n---\n\n{body}")
    skill("tmux-enter-swallow",
          "Fix a tmux pane that swallows the Enter key when text and submit are sent together.")
    skill("azure-deploy-proof",
          "Prove an Azure App Service deployment landed when the platform reports success.")
    skill("kiln-calibration", "Calibrate kiln thermocouple drift across firing cycles.")
    for i in range(6):
        skill(f"filler-{i}", f"Unrelated placeholder capability {i}.")


def run(prompt, root, **env):
    """Returns (completed_process, parsed_stdout_or_None)."""
    e = dict(os.environ, SKILLS_MCP_DIR=root)
    e.pop("SKILLS_MCP_ROOTS", None)
    e.update({k: str(v) for k, v in env.items()})
    p = subprocess.run([sys.executable, HOOK],
                       input=json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": prompt}),
                       capture_output=True, text=True, env=e)
    out = p.stdout.strip()
    return p, (json.loads(out) if out else None)


def ctx(data):
    return data["hookSpecificOutput"]["additionalContext"] if data else ""


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "skills")
        os.makedirs(root)
        fixture(root)

        p, data = run("how do I stop tmux from swallowing the enter key on a pane", root,
                      SKILLS_HOOK_MIN_SCORE=1)
        check("fires on a matching prompt", data is not None)
        check("emits the UserPromptSubmit hookSpecificOutput shape",
              data and data["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit")
        check("ranks the right skill into the context",
              "tmux-enter-swallow" in ctx(data))
        check("labels the injection as suggestions, not orders",
              "suggestions, not instructions" in ctx(data))
        check("exits 0 so it can never block the prompt", p.returncode == 0)

        # The bug this hook shipped with once: a hit whose DESCRIPTION matches was
        # filtered out as "redundant", leaving only weaker, wronger hits.
        _, dep = run("the deploy reported success but I want proof it is serving", root,
                     SKILLS_HOOK_MIN_SCORE=1)
        check("a hit that matches on description is NOT filtered out",
              "azure-deploy-proof" in ctx(dep))

        # Every quiet path must be quiet on ALL THREE channels. An earlier build
        # crashed on the skip paths: stdout was empty so a stdout-only assertion
        # passed, while a NameError traceback went to stderr on every short
        # prompt and every slash command.
        def quiet(label, prompt, **env):
            proc, data = run(prompt, root, **env)
            check(f"stays silent: {label}", data is None)
            check(f"  exit 0: {label}", proc.returncode == 0)
            check(f"  clean stderr: {label}", proc.stderr.strip() == "")

        quiet("slash command", "/orches build the thing please", SKILLS_HOOK_MIN_SCORE=1)
        quiet("too-short prompt", "ok", SKILLS_HOOK_MIN_SCORE=1)
        quiet("no searchable terms", "ช่วยดูให้หน่อยว่าอันไหนดีกว่ากันสำหรับงานนี้",
              SKILLS_HOOK_MIN_SCORE=1)
        quiet("nothing clears the threshold",
              "how do I stop tmux from swallowing the enter key on a pane",
              SKILLS_HOOK_MIN_SCORE=9999)

        _, k1 = run("tmux enter key deployment kiln thermocouple", root,
                    SKILLS_HOOK_MIN_SCORE=1, SKILLS_HOOK_K=1)
        check("K caps how many skills are injected",
              len([l for l in ctx(k1).splitlines() if l.startswith("- ")]) == 1)

        p_bad = subprocess.run([sys.executable, HOOK], input="{ not json",
                               capture_output=True, text=True,
                               env=dict(os.environ, SKILLS_MCP_DIR=root))
        check("malformed stdin exits 0 and stays silent",
              p_bad.returncode == 0 and not p_bad.stdout.strip() and not p_bad.stderr.strip())

        p_gone = subprocess.run([sys.executable, HOOK],
                                input=json.dumps({"hook_event_name": "UserPromptSubmit",
                                                  "prompt": "tmux enter key swallowed on a pane"}),
                                capture_output=True, text=True,
                                env=dict(os.environ, SKILLS_MCP_DIR=os.path.join(tmp, "gone")))
        check("a missing skills dir exits 0 and stays silent",
              p_gone.returncode == 0 and not p_gone.stdout.strip() and not p_gone.stderr.strip())

        _, other = run("tmux enter key swallowed on a pane", root, SKILLS_HOOK_MIN_SCORE=1)
        p_ev = subprocess.run([sys.executable, HOOK],
                              input=json.dumps({"hook_event_name": "PreToolUse",
                                                "prompt": "tmux enter key swallowed on a pane"}),
                              capture_output=True, text=True,
                              env=dict(os.environ, SKILLS_MCP_DIR=root, SKILLS_HOOK_MIN_SCORE="1"))
        check("ignores a hook event that is not UserPromptSubmit",
              other is not None and not p_ev.stdout.strip())

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
