#!/usr/bin/env python3
"""Mechanical tests for auto_skill.py — the non-blocking skill writer.

Runs the CLI in a throwaway temp dir and asserts on its JSON output + the
files it writes. Dependency-free (stdlib only). Run:  python3 test_auto_skill.py
"""
import json
import os
import subprocess
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(HERE), "scripts", "auto_skill.py")
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "scripts"))
import auto_skill  # noqa: E402  # reuse _body_hash / _read_frontmatter helpers

_passed = 0
_failed = 0


def _yaml_fm(text):
    """Parse the frontmatter block with PyYAML: dict on success, False when the
    block is present but invalid, None when PyYAML is not installed. The suite
    stays stdlib-only — this assertion just gets stronger when PyYAML is around,
    which is what skills-mcp actually parses SKILL.md with at runtime."""
    try:
        import yaml  # type: ignore
    except Exception:
        return None
    try:
        parsed = yaml.safe_load(text.split("---", 2)[1])
    except Exception:
        return False
    return parsed if isinstance(parsed, dict) else False


def run(*args, cwd=None, env=None):
    """Invoke auto_skill.py, return (exit_code, parsed_json_or_None, raw_stdout)."""
    full_env = dict(os.environ)
    full_env.setdefault("AUTO_SKILL_SOURCE", "test-oracle")  # creator is mandatory
    if env:
        full_env.update(env)
    proc = subprocess.run(
        [sys.executable, SCRIPT, *args],
        cwd=cwd, capture_output=True, text=True, env=full_env,
    )
    out = proc.stdout.strip()
    parsed = None
    try:
        parsed = json.loads(out)
    except Exception:
        pass
    return proc.returncode, parsed, proc.stdout + proc.stderr


def check(name, cond, detail=""):
    global _passed, _failed
    if cond:
        _passed += 1
        print(f"  PASS  {name}")
    else:
        _failed += 1
        print(f"  FAIL  {name}  {detail}")


def main():
    work = tempfile.mkdtemp(prefix="autoskill-test-")
    skills = os.path.join(work, ".claude", "skills")
    try:
        # 1. create -> written, valid frontmatter + provenance
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nRun tests then `fly deploy`.",
            "--dir", skills, "--trigger", "reusable-workflow",
        )
        skill_md = os.path.join(skills, "deploy-fly", "SKILL.md")
        check("create returns created", js and js.get("status") == "created", raw)
        check("create exit 0", code == 0, f"code={code}")
        check("SKILL.md written", os.path.isfile(skill_md))
        content = open(skill_md).read() if os.path.isfile(skill_md) else ""
        # Assert PARSED values, not raw substrings: free-text frontmatter values are
        # single-quoted so a description containing ': ' stays valid YAML, and a raw
        # "description: X" match would break on the quotes for no good reason.
        fm0, _ = auto_skill._read_frontmatter(content)
        check("frontmatter installer stamp", fm0.get("installer") == "auto-skill")
        check("frontmatter has description", fm0.get("description") == "Deploy to Fly.io")
        check("frontmatter has content_hash", "content_hash:" in content)
        check("frontmatter has trigger", fm0.get("trigger") == "reusable-workflow")
        check("frontmatter records creator", fm0.get("created_by") == "test-oracle")
        check("description is emitted single-quoted",
              "description: 'Deploy to Fly.io'" in content)

        # A description containing ': ' is the common real shape
        # ("Use when <trigger>: <behavior>") and used to make the frontmatter
        # invalid YAML, which silently dropped every nested block in the file.
        code, js, raw = run(
            "create", "--name", "colon-desc", "--desc", "Use when X breaks: do Y", "--body", "z",
            "--dir", skills,
        )
        cpath = os.path.join(skills, "colon-desc", "SKILL.md")
        ctext = open(cpath).read() if os.path.isfile(cpath) else ""
        check("colon-in-description is quoted in the file",
              "description: 'Use when X breaks: do Y'" in ctext, raw)
        check("colon-in-description readable by the flat reader",
              auto_skill._read_frontmatter(ctext)[0].get("description") == "Use when X breaks: do Y")
        cyaml = _yaml_fm(ctext)
        check("colon-in-description parses as YAML (skipped without PyYAML)",
              cyaml is None or (isinstance(cyaml, dict)
                               and cyaml.get("description") == "Use when X breaks: do Y"))

        # an apostrophe must survive the '' escaping
        code, js, raw = run(
            "create", "--name", "quote-desc", "--desc", "it's tricky: really", "--body", "z",
            "--dir", skills,
        )
        qtext = open(os.path.join(skills, "quote-desc", "SKILL.md")).read()
        qyaml = _yaml_fm(qtext)
        check("apostrophe escaped as '' and round-trips",
              auto_skill._read_frontmatter(qtext)[0].get("description") == "it's tricky: really"
              and (qyaml is None or (isinstance(qyaml, dict)
                                     and qyaml.get("description") == "it's tricky: really")), raw)

        # 2. validate passes on the generated file
        code, js, raw = run("validate", skill_md)
        check("validate ok on generated", code == 0 and js and js.get("valid") is True, raw)

        # 3. idempotent: same name + same body -> exists-identical, no dup, exit 0
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nRun tests then `fly deploy`.",
            "--dir", skills,
        )
        check("re-create identical -> exists-identical",
              js and js.get("status") == "exists-identical", raw)
        check("re-create identical exit 0", code == 0, f"code={code}")

        # 4. conflict: same name, DIFFERENT body, no --force -> refused, exit != 0, original intact
        before = open(skill_md).read() if os.path.isfile(skill_md) else ""
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nTOTALLY DIFFERENT BODY.",
            "--dir", skills,
        )
        check("conflict -> refused-conflict", js and js.get("status") == "refused-conflict", raw)
        check("conflict exit != 0", code != 0, f"code={code}")
        check("conflict leaves original intact", open(skill_md).read() == before)

        # 5. --force overwrites on conflict
        code, js, raw = run(
            "create", "--name", "deploy-fly", "--desc", "Deploy to Fly.io",
            "--body", "# /deploy-fly\n\nTOTALLY DIFFERENT BODY.", "--force",
            "--dir", skills,
        )
        check("force -> created", js and js.get("status") == "created", raw)
        check("force actually overwrote", "TOTALLY DIFFERENT BODY" in open(skill_md).read())

        # 6. a non-kebab name is REPAIRED, not rejected (repair inputs, don't
        #    bounce them — a refusal at end-of-task just burns a turn)
        code, js, raw = run(
            "create", "--name", "Bad Name!", "--desc", "x",
            "--body", "y", "--dir", skills,
        )
        check("non-kebab name -> created", js and js.get("status") == "created", raw)
        check("non-kebab name normalized to kebab", js.get("name") == "bad-name", raw)
        check("name repair is reported", js.get("repaired", {}).get("name", {}).get("given")
              == "Bad Name!", raw)
        check("non-kebab name exit 0", code == 0, f"code={code}")

        # 6b. a name that cannot be repaired into a kebab is still refused
        code, js, raw = run(
            "create", "--name", "!!!", "--desc", "x",
            "--body", "y", "--dir", skills,
        )
        check("unrepairable name -> invalid", js and js.get("status") == "invalid", raw)
        check("unrepairable name exit != 0", code != 0, f"code={code}")

        # 6c. an over-long description is truncated + disclosed, never refused
        long_desc = "Use when " + ("some very wordy trigger phrase " * 20)
        code, js, raw = run(
            "create", "--name", "long-desc-skill", "--desc", long_desc,
            "--body", "y", "--dir", skills,
        )
        check("long desc -> created", js and js.get("status") == "created", raw)
        check("long desc exit 0", code == 0, f"code={code}")
        rep = (js.get("repaired") or {}).get("description") or {}
        check("long desc reports original length", rep.get("given_chars") == len(long_desc.strip()),
              raw)
        written = open(os.path.join(skills, "long-desc-skill", "SKILL.md")).read()
        dfm, _ = auto_skill._read_frontmatter(written)
        dwritten = dfm.get("description", "")
        check("written desc is within the cap", len(dwritten) <= 200, "len=%d" % len(dwritten))
        check("written desc keeps the trigger prefix", dwritten.startswith("Use when "), dwritten)
        check("written desc is marked as clipped", dwritten.endswith("…"), dwritten)
        check("truncated desc still parses as YAML", _yaml_fm(written) is not False, written[:200])

        # 7. empty description rejected
        code, js, raw = run(
            "create", "--name", "ok-name", "--desc", "",
            "--body", "y", "--dir", skills,
        )
        check("empty desc -> invalid", js and js.get("status") == "invalid", raw)

        # 8. stage mode writes to .pending-skills, NOT live
        code, js, raw = run(
            "create", "--name", "staged-skill", "--desc", "A staged one",
            "--body", "# /staged-skill\n\nbody", "--dir", skills, "--stage",
        )
        live = os.path.join(skills, "staged-skill", "SKILL.md")
        pend = os.path.join(skills, ".pending-skills", "staged-skill", "SKILL.md")
        queue = os.path.join(skills, ".pending-skills", "queue.md")
        check("stage -> staged", js and js.get("status") == "staged", raw)
        check("stage did NOT write live skill", not os.path.exists(live))
        check("stage wrote pending file", os.path.isfile(pend))
        check("stage appended to queue.md", os.path.isfile(queue))

        # 9. validate fails on malformed SKILL.md (no description)
        bad_dir = os.path.join(skills, "bad-skill")
        os.makedirs(bad_dir, exist_ok=True)
        open(os.path.join(bad_dir, "SKILL.md"), "w").write("---\nname: bad-skill\n---\n\n# /bad-skill\n")
        code, js, raw = run("validate", os.path.join(bad_dir, "SKILL.md"))
        check("validate fails on missing description", code != 0 and js and js.get("valid") is False, raw)

        # 10. list shows auto-skill skills
        code, js, raw = run("list", "--dir", skills)
        names = {e.get("name") for e in js} if isinstance(js, list) else set()
        check("list includes created skill", "deploy-fly" in names, raw)

        # 11. AUTO_SKILL_DIR env sets the landing dir when no --dir/--global
        env_dir = os.path.join(work, "envhome", "skills")
        code, js, raw = run(
            "create", "--name", "env-skill", "--desc", "Lands via env",
            "--body", "# /env-skill\n\nbody", env={"AUTO_SKILL_DIR": env_dir},
        )
        check("env: create ok", js and js.get("status") == "created", raw)
        check("env: landed in AUTO_SKILL_DIR",
              os.path.isfile(os.path.join(env_dir, "env-skill", "SKILL.md")), raw)

        # 12. explicit --dir overrides AUTO_SKILL_DIR
        code, js, raw = run(
            "create", "--name", "dir-wins", "--desc", "dir over env",
            "--body", "# /dir-wins\n\nbody", "--dir", skills,
            env={"AUTO_SKILL_DIR": env_dir},
        )
        check("--dir overrides env",
              os.path.isfile(os.path.join(skills, "dir-wins", "SKILL.md"))
              and not os.path.exists(os.path.join(env_dir, "dir-wins")), raw)

        # 13. creator is MANDATORY: no --source and empty AUTO_SKILL_SOURCE -> invalid
        code, js, raw = run(
            "create", "--name", "no-owner", "--desc", "should be refused",
            "--body", "x", "--dir", skills, env={"AUTO_SKILL_SOURCE": ""},
        )
        check("missing creator -> invalid", js and js.get("status") == "invalid", raw)
        check("missing creator exit != 0", code != 0, f"code={code}")
        check("missing creator wrote nothing", not os.path.exists(os.path.join(skills, "no-owner")))

        # 14. --source overrides AUTO_SKILL_SOURCE and is recorded as created_by
        code, js, raw = run(
            "create", "--name", "owned-skill", "--desc", "owned", "--body", "x",
            "--dir", skills, "--source", "bob-oracle",
        )
        owned = os.path.join(skills, "owned-skill", "SKILL.md")
        check("--source create ok", js and js.get("status") == "created", raw)
        check("--source recorded as created_by",
              os.path.isfile(owned)
              and auto_skill._read_frontmatter(open(owned).read())[0].get("created_by") == "bob-oracle",
              raw)

        # 15. --category stamped into frontmatter + surfaced by list
        code, js, raw = run(
            "create", "--name", "cat-skill", "--desc", "has a category", "--body", "x",
            "--dir", skills, "--category", "git-workflows",
        )
        catmd = os.path.join(skills, "cat-skill", "SKILL.md")
        check("category create ok", js and js.get("status") == "created", raw)
        check("category stamped",
              os.path.isfile(catmd)
              and auto_skill._read_frontmatter(open(catmd).read())[0].get("category") == "git-workflows",
              raw)
        code, js, raw = run("list", "--dir", skills)
        entry = next((e for e in js if e.get("name") == "cat-skill"), {}) if isinstance(js, list) else {}
        check("list surfaces category", entry.get("category") == "git-workflows", raw)

        # 16. a category with spaces/slash is REPAIRED into one kebab segment
        code, js, raw = run(
            "create", "--name", "bad-cat", "--desc", "x", "--body", "y",
            "--dir", skills, "--category", "Bad Cat/x",
        )
        check("messy category -> created", js and js.get("status") == "created", raw)
        check("messy category normalized",
              (js.get("repaired") or {}).get("category", {}).get("used") == "bad-cat-x", raw)
        bcfm, _ = auto_skill._read_frontmatter(
            open(os.path.join(skills, "bad-cat", "SKILL.md")).read())
        check("repaired category written", bcfm.get("category") == "bad-cat-x", raw)

        # 17. CONCURRENCY (the race a plain exists()-check can't stop): many workers
        #     create the SAME name with DIFFERENT bodies at the same instant. With
        #     check-then-write, several can all see "no file yet" and clobber each
        #     other — a skill lost silently. Exclusive create must let exactly ONE
        #     win; every other worker sees the clash and is refused, never overwritten.
        race_name = "race-skill"
        race_dir = os.path.join(work, "race", "skills")
        os.makedirs(race_dir, exist_ok=True)
        N = 24
        procs = [
            subprocess.Popen(
                [sys.executable, SCRIPT, "create", "--name", race_name,
                 "--desc", "concurrent create", "--source", "oracle-%d" % i,
                 "--body", "# /%s\n\nvariant %d\n" % (race_name, i), "--dir", race_dir],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            for i in range(N)
        ]
        statuses = []
        for p in procs:
            out, _ = p.communicate()
            try:
                statuses.append(json.loads(out.strip()).get("status"))
            except Exception:
                statuses.append("unparseable:%r" % out)
        created = statuses.count("created")
        check("concurrent: exactly one winner (no silent clobber)",
              created == 1, "created=%d statuses=%s" % (created, statuses))
        check("concurrent: losers refused, nobody overwritten",
              all(s in ("created", "refused-conflict") for s in statuses),
              "statuses=%s" % statuses)
        race_md = os.path.join(race_dir, race_name, "SKILL.md")
        rfm, _rbody = auto_skill._read_frontmatter(open(race_md).read())
        valid = {auto_skill._body_hash("# /%s\n\nvariant %d\n" % (race_name, i)) for i in range(N)}
        check("concurrent: survivor is one intact variant (no torn write)",
              rfm.get("content_hash") in valid, "content_hash=%s" % rfm.get("content_hash"))

        # 18. TOCTOU race made DETERMINISTIC: a rival oracle's DIFFERENT skill lands
        #     on disk in the tiny window after our existence check but before our
        #     write. We force that ordering by dropping the rival's file during dir
        #     creation. A check-then-write clobbers the rival silently; an exclusive
        #     create must refuse and leave the rival's file untouched. This is the
        #     exact "two oracles, same name, at once" case, minus the timing luck.
        import io as _io, contextlib as _ctx
        toctou_dir = os.path.join(work, "toctou", "skills")
        tname = "toctou-skill"
        tdest = os.path.join(toctou_dir, tname, "SKILL.md")
        _real_makedirs = os.makedirs

        def _rival_makedirs(path, *pa, **kw):
            _real_makedirs(path, *pa, **kw)
            # rival writes first, inside the check->write gap
            if os.path.basename(path.rstrip(os.sep)) == tname and not os.path.exists(tdest):
                with open(tdest, "x") as rf:
                    rf.write("---\nname: %s\ndescription: rival\ninstaller: auto-skill\n"
                             "content_hash: RIVALHASH\n---\n\nrival body keep me\n" % tname)

        parser = auto_skill.build_parser()
        ns = parser.parse_args(["create", "--name", tname, "--desc", "mine",
                                "--body", "# /%s\n\nmy body clobbers?" % tname,
                                "--dir", toctou_dir, "--source", "me-oracle"])
        _buf = _io.StringIO()
        auto_skill.os.makedirs = _rival_makedirs
        try:
            with _ctx.redirect_stdout(_buf):
                ns.fn(ns)
        except SystemExit:
            pass
        finally:
            auto_skill.os.makedirs = _real_makedirs
        try:
            tres = json.loads(_buf.getvalue().strip() or "{}")
        except Exception:
            tres = {}
        survived = open(tdest).read() if os.path.exists(tdest) else ""
        check("toctou: rival refused, not clobbered",
              tres.get("status") == "refused-conflict", "res=%s" % tres)
        check("toctou: rival body still on disk",
              "rival body keep me" in survived, "survived=%s" % survived[:80])

        # 19. STAGE conflict (stage now shares the live path's first-writer-wins rule):
        #     staging a name whose pending file already holds DIFFERENT content, with no
        #     --force, is refused and leaves the existing pending file intact.
        st_dir = os.path.join(work, "stage2", "skills")
        code, js, raw = run("create", "--name", "dup-stage", "--desc", "first", "--stage",
                            "--body", "# /dup-stage\n\nfirst body", "--dir", st_dir)
        check("stage first -> staged", js and js.get("status") == "staged", raw)
        s_pend = os.path.join(st_dir, ".pending-skills", "dup-stage", "SKILL.md")
        first_staged = open(s_pend).read() if os.path.isfile(s_pend) else ""
        code, js, raw = run("create", "--name", "dup-stage", "--desc", "second", "--stage",
                            "--body", "# /dup-stage\n\nDIFFERENT second body", "--dir", st_dir)
        check("stage conflict -> refused-conflict", js and js.get("status") == "refused-conflict", raw)
        check("stage conflict exit != 0", code != 0, "code=%d" % code)
        check("stage conflict leaves first pending intact", open(s_pend).read() == first_staged)

        # 20. STAGE TOCTOU (deterministic): a rival's pending file lands in the
        #     check->write gap; exclusive create must refuse, not overwrite it.
        st2 = os.path.join(work, "stage-toctou", "skills")
        sname = "race-stage"
        s2_pend = os.path.join(st2, ".pending-skills", sname, "SKILL.md")
        _real_md2 = os.makedirs

        def _rival_md2(path, *pa, **kw):
            _real_md2(path, *pa, **kw)
            if os.path.basename(path.rstrip(os.sep)) == sname and not os.path.exists(s2_pend):
                with open(s2_pend, "x") as rf:
                    rf.write("---\nname: %s\ndescription: rival\ncontent_hash: RIVALHASH\n---\n\n"
                             "rival staged keep me\n" % sname)

        ns2 = auto_skill.build_parser().parse_args(
            ["create", "--name", sname, "--desc", "mine", "--stage",
             "--body", "# /%s\n\nmy staged loses?" % sname, "--dir", st2, "--source", "me-oracle"])
        _buf2 = _io.StringIO()
        auto_skill.os.makedirs = _rival_md2
        try:
            with _ctx.redirect_stdout(_buf2):
                ns2.fn(ns2)
        except SystemExit:
            pass
        finally:
            auto_skill.os.makedirs = _real_md2
        try:
            sres = json.loads(_buf2.getvalue().strip() or "{}")
        except Exception:
            sres = {}
        s2_surv = open(s2_pend).read() if os.path.exists(s2_pend) else ""
        check("stage toctou: rival refused, not clobbered",
              sres.get("status") == "refused-conflict", "res=%s" % sres)
        check("stage toctou: rival pending body intact",
              "rival staged keep me" in s2_surv, "survived=%s" % s2_surv[:80])

        # ---- near-duplicate reporting -------------------------------------
        # The name-clash guard catches `create --name x` twice. It cannot catch
        # the same procedure arriving under a second name, which is how the
        # catalog actually grows (8.9 skills/week, measured). This check reports
        # and NEVER refuses: a capture lost to a false positive costs more than
        # a duplicate skill costs, so every assertion below pins that down.
        dup = os.path.join(work, "dupes")
        run("create", "--name", "restart-nginx-after-cert-renew",
            "--desc", "Restart nginx after renewing a TLS certificate with certbot",
            "--body", "steps", "--dir", dup)

        code, js, raw = run(
            "create", "--name", "reload-nginx-on-certbot-renewal",
            "--desc", "Reload nginx when certbot renews the TLS certificate",
            "--body", "steps", "--dir", dup)
        check("near-duplicate is reported", bool(js and js.get("near_duplicates")), raw)
        check("near-duplicate names the sibling",
              bool(js) and any(d["name"] == "restart-nginx-after-cert-renew"
                               for d in js.get("near_duplicates") or []), raw)
        check("near-duplicate does NOT block the write",
              bool(js) and js.get("status") == "created" and code == 0,
              "code=%s js=%s" % (code, js))
        check("near-duplicate still writes the file",
              os.path.isfile(os.path.join(dup, "reload-nginx-on-certbot-renewal",
                                          "SKILL.md")))
        check("near-duplicate message names the overlap",
              bool(js) and "restart-nginx-after-cert-renew" in (js.get("message") or ""),
              raw)

        code, js, raw = run(
            "create", "--name", "convert-heic-to-jpeg",
            "--desc", "Batch convert HEIC photos to JPEG with sips",
            "--body", "steps", "--dir", dup)
        check("an unrelated skill reports no duplicates",
              bool(js) and "near_duplicates" not in js, raw)

        code, js, raw = run(
            "create", "--name", "restart-nginx-after-tls-renewal",
            "--desc", "Restart nginx after renewing the TLS certificate via certbot",
            "--body", "steps", "--dir", dup,
            env={"AUTO_SKILL_DUP_THRESHOLD": "0"})
        check("AUTO_SKILL_DUP_THRESHOLD=0 disables the check",
              bool(js) and "near_duplicates" not in js, raw)

        # Report-only means it must survive a catalog it cannot read. A directory
        # with no SKILL.md, and one that is not a directory at all, are both
        # normal on a real machine.
        os.makedirs(os.path.join(dup, "empty-skill-dir"), exist_ok=True)
        open(os.path.join(dup, "stray-file.md"), "w").write("not a skill")
        code, js, raw = run(
            "create", "--name", "restart-nginx-after-renewal-again",
            "--desc", "Restart nginx after renewing the TLS certificate with certbot",
            "--body", "steps", "--dir", dup)
        check("unreadable catalog entries do not break create",
              bool(js) and js.get("status") == "created" and code == 0, raw)
        check("duplicate check still works past an unreadable entry",
              bool(js) and bool(js.get("near_duplicates")), raw)

        # A description made only of stopwords must not match everything.
        check("stopwords alone produce no tokens",
              auto_skill._dup_tokens("use when the a an and or to of for") == set())
        check("overlap is against the SMALLER token set",
              auto_skill._near_duplicates(dup, "zzz-nonexistent", "") == [])
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{_passed} passed, {_failed} failed")
    sys.exit(1 if _failed else 0)


if __name__ == "__main__":
    main()
