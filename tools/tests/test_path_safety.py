#!/usr/bin/env python3
"""Path safety for the two fleet tools that DELETE before they write.

Both tools build a destination directory out of frontmatter that they do not own
(`name:` and `category:` come from whatever SKILL.md is on disk) and then call
`shutil.rmtree(dest)` on it. `os.path.join` has two behaviours that turn that into
an arbitrary-path delete:

  * a `..` segment walks out of the intended root
  * an ABSOLUTE segment discards every prefix before it
    (`os.path.join("/repo/skills", "/home/me/.claude")` -> `/home/me/.claude`)

collect_commit.py is on the weekly cron WITH `--push` (crontab: `30 17 * * 0`), so
nobody is watching when it runs, and it `git add -A` + commits whatever landed
inside the repo afterwards. auto_skill.py (the writer) does validate name/category,
but it is not the only writer: `installer: auto-skill` is one line of text that a
hand-written, uploaded, or patched SKILL.md can carry too — and ~/.claude/skills
today really does hold names like `Word / DOCX` and `<name>`.

So validation has to sit at the destructive step, not only at the writer. These
tests are the red proof: every one of them FAILS against the pre-fix tools.

Stdlib only.  Run:  python3 test_path_safety.py
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
COLLECT = os.path.join(TOOLS, "collect_commit.py")
SYNC = os.path.join(TOOLS, "sync_skills.py")

_p = _f = 0


def check(name, cond, detail=""):
    global _p, _f
    if cond:
        _p += 1
        print(f"  PASS  {name}")
    else:
        _f += 1
        print(f"  FAIL  {name}  {detail}")


def sh(*args):
    r = subprocess.run(args, capture_output=True, text=True)
    try:
        return r.returncode, json.loads(r.stdout.strip()), r.stdout + r.stderr
    except Exception:
        return r.returncode, None, r.stdout + r.stderr


def write_skill(src, dirname, name, category, body="# body\n\nsteps"):
    """Hand-write a SKILL.md — the point is values the WRITER would have refused.
    The directory name on disk is deliberately harmless: the tools key off the
    frontmatter `name:`, not the folder, so that is where the escape lives."""
    d = os.path.join(src, dirname)
    os.makedirs(d, exist_ok=True)
    digest = hashlib.sha256(body.strip().encode("utf-8")).hexdigest()
    open(os.path.join(d, "SKILL.md"), "w").write(
        "---\n"
        f"name: {name}\n"
        f"description: {dirname} for the path-safety test\n"
        "installer: auto-skill\n"
        "created_at: 2026-08-20T00:00:00+07:00\n"
        "created_session: \n"
        "trigger: 'reusable-workflow'\n"
        "created_by: 'path-safety-test'\n"
        f"category: {category}\n"
        f"content_hash: {digest}\n"
        "---\n\n" + body
    )
    return d


def escaped(root, *segments):
    """Where the join REALLY lands. Asserting on the path you *meant* is how a
    traversal test passes while the traversal happens: dest/../../X normalizes
    one level ABOVE the work dir, so a check under work/ never sees it. This
    red-proof produced a real /tmp/SYNC_PWNED before the assertion was fixed."""
    return os.path.normpath(os.path.join(root, *segments))


def victim(work, tag):
    """A directory OUTSIDE both roots holding one irreplaceable file."""
    v = os.path.join(work, tag, "keepme")
    os.makedirs(v, exist_ok=True)
    open(os.path.join(v, "important.txt"), "w").write("the only copy\n")
    return os.path.join(work, tag)


def alive(v):
    return os.path.isfile(os.path.join(v, "keepme", "important.txt"))


def rejected_names(js):
    """Every shape a report could take — the assertion is 'it told someone',
    not the exact key, so a tool may report differently and still pass."""
    if not js:
        return []
    out = []
    for entry in js.get("rejected", []) or []:
        out.append(entry.get("name") if isinstance(entry, dict) else str(entry))
    return [o for o in out if o]


def main():
    work = tempfile.mkdtemp(prefix="path-safety-")
    try:
        # ── collect_commit: `..` in category walks out of skills/ into the repo root ──
        src = os.path.join(work, "src1")
        repo = os.path.join(work, "repo1")
        os.makedirs(os.path.join(repo, "skills"))
        subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
        write_skill(src, "good", "good-skill", "testing")
        write_skill(src, "evil-cat", "evil-cat-skill", "../../ESCAPED")
        code, js, raw = sh(sys.executable, COLLECT, "--repo", repo, "--from", src)
        out1 = escaped(os.path.join(repo, "skills"), "../../ESCAPED", "evil-cat-skill")
        check("C1 category '..' ไม่หลุดออกนอก skills/",
              not os.path.exists(out1), f"หลุดไปที่ {out1}\n{raw}")
        check("C1 รายงานว่าปฏิเสธ (ไม่เงียบ)",
              "evil-cat-skill" in rejected_names(js), raw)
        check("C1 สกิลปกติในรันเดียวกันยังเก็บได้",
              os.path.isfile(os.path.join(repo, "skills", "testing", "good-skill", "SKILL.md")), raw)

        # ── collect_commit: `..` in the NAME does the same ──
        src = os.path.join(work, "src2")
        repo = os.path.join(work, "repo2")
        os.makedirs(os.path.join(repo, "skills"))
        subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
        write_skill(src, "evil-name", "../../PWNED", "testing")
        code, js, raw = sh(sys.executable, COLLECT, "--repo", repo, "--from", src)
        out2 = escaped(os.path.join(repo, "skills"), "testing", "../../PWNED")
        check("C2 name '..' ไม่หลุดออกนอก skills/",
              not os.path.exists(out2), f"หลุดไปที่ {out2}\n{raw}")
        check("C2 รายงานว่าปฏิเสธ", bool(rejected_names(js)), raw)

        # ── collect_commit: ABSOLUTE category = rmtree of a real directory ──
        #   os.path.join(skills_root, "/work/v1") -> "/work/v1"  (prefix discarded)
        v = victim(work, "v1")
        src = os.path.join(work, "src3")
        repo = os.path.join(work, "repo3")
        os.makedirs(os.path.join(repo, "skills"))
        subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
        write_skill(src, "evil-abs", "keepme", v)
        code, js, raw = sh(sys.executable, COLLECT, "--repo", repo, "--from", src)
        check("C3 category แบบ absolute ไม่ลบโฟลเดอร์จริงข้างนอก", alive(v), raw)
        check("C3 รายงานว่าปฏิเสธ", bool(rejected_names(js)), raw)

        # ── sync_skills: `..` in the name escapes the dest ──
        repo = os.path.join(work, "repo4")
        dest = os.path.join(work, "dest4")
        os.makedirs(os.path.join(repo, "skills", "testing"))
        write_skill(os.path.join(repo, "skills", "testing"), "good", "good-skill", "testing")
        write_skill(os.path.join(repo, "skills", "testing"), "evil", "../../SYNC_PWNED", "testing")
        code, js, raw = sh(sys.executable, SYNC, "--repo", repo, "--dest", dest)
        out3 = escaped(dest, "../../SYNC_PWNED")
        check("S1 name '..' ไม่หลุดออกนอก dest",
              not os.path.exists(out3), f"หลุดไปที่ {out3}\n{raw}")
        check("S1 รายงานว่าปฏิเสธ", "../../SYNC_PWNED" in rejected_names(js)
              or bool(rejected_names(js)), raw)
        check("S1 สกิลปกติยัง sync ได้",
              os.path.isfile(os.path.join(dest, "good-skill", "SKILL.md")), raw)

        # ── sync_skills: ABSOLUTE name = rmtree of a real directory ──
        v2 = victim(work, "v2")
        repo = os.path.join(work, "repo5")
        dest = os.path.join(work, "dest5")
        os.makedirs(os.path.join(repo, "skills", "testing"))
        write_skill(os.path.join(repo, "skills", "testing"), "evil-abs",
                    os.path.join(v2, "keepme"), "testing")
        code, js, raw = sh(sys.executable, SYNC, "--repo", repo, "--dest", dest)
        check("S2 name แบบ absolute ไม่ลบโฟลเดอร์จริงข้างนอก", alive(v2), raw)
        check("S2 รายงานว่าปฏิเสธ", bool(rejected_names(js)), raw)

        # ── no-regression: a clean run must stay byte-identical in behaviour ──
        repo = os.path.join(work, "repo6")
        dest = os.path.join(work, "dest6")
        src = os.path.join(work, "src6")
        os.makedirs(os.path.join(repo, "skills"))
        subprocess.run(["git", "-C", repo, "init", "-q"], check=True)
        write_skill(src, "a", "alpha-skill", "git")
        write_skill(src, "b", "beta-skill", "tmux")
        code, js, raw = sh(sys.executable, COLLECT, "--repo", repo, "--from", src)
        check("N1 สกิลสะอาดถูกเก็บครบ",
              js and sorted(js.get("committed", [])) == ["alpha-skill", "beta-skill"], raw)
        check("N1 ไม่มี rejected ในรันที่สะอาด", not rejected_names(js), raw)
        code, js, raw = sh(sys.executable, SYNC, "--repo", repo, "--dest", dest)
        check("N2 sync สกิลสะอาดครบ",
              os.path.isfile(os.path.join(dest, "alpha-skill", "SKILL.md"))
              and os.path.isfile(os.path.join(dest, "beta-skill", "SKILL.md")), raw)
        check("N2 sync ไม่มี rejected ในรันที่สะอาด", not rejected_names(js), raw)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    print(f"\n{_p} passed, {_f} failed")
    sys.exit(1 if _f else 0)


if __name__ == "__main__":
    main()
