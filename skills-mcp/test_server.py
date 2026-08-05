#!/usr/bin/env python3
"""End-to-end test for skills-mcp: spawn the real server over stdio, drive the
MCP handshake, and assert every feature (1-5) incl. security edge cases."""

import json
import os
import subprocess
import sys
import tempfile
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "server.py")
HOOK = os.path.join(HERE, "inventory-hook.py")

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


def w(path, text):
    with open(path, "w") as f:
        f.write(textwrap.dedent(text))


def make_fixture(root):
    a = os.path.join(root, "alpha-skill")
    os.makedirs(os.path.join(a, "references"))
    w(os.path.join(a, "SKILL.md"), """\
        ---
        name: alpha-skill
        description: "Use when doing alpha things: the alpha procedure."
        category: testing
        trigger: reusable-workflow
        content_hash: deadbeef
        ---
        # Alpha
        Body of alpha. See references/detail.md for more.
        Run: OLD_COMMAND --flag
        """)
    w(os.path.join(a, "references", "detail.md"), "# Detail\nDeep alpha reference content.\n")

    b = os.path.join(root, "beta-skill")
    os.makedirs(b)
    w(os.path.join(b, "SKILL.md"), """\
        ---
        name: beta-skill
        description: Plain beta description with a colon: here.
        category: other
        ---
        # Beta
        Body of beta.
        """)

    # gamma: needs an MCP server that is NOT registered -> hidden (Feature 4)
    g = os.path.join(root, "gamma-skill")
    os.makedirs(g)
    w(os.path.join(g, "SKILL.md"), """\
        ---
        name: gamma-skill
        description: Needs a phantom MCP server.
        requires:
          mcp: [nonexistent-xyz-server]
        ---
        # Gamma
        Body of gamma.
        """)

    # delta: needs a specific agent tool (Feature 4 via agent_tools)
    d = os.path.join(root, "delta-skill")
    os.makedirs(d)
    w(os.path.join(d, "SKILL.md"), """\
        ---
        name: delta-skill
        description: Needs the FooTool.
        requires:
          tools: [FooTool]
        ---
        # Delta
        Body of delta.
        """)

    # epsilon: needs a missing command (Feature 2 readiness, not hidden)
    e = os.path.join(root, "epsilon-skill")
    os.makedirs(e)
    w(os.path.join(e, "SKILL.md"), """\
        ---
        name: epsilon-skill
        description: Needs a missing binary.
        requires:
          commands: [definitely-not-a-real-binary-xyz]
          env: [SKILLS_MCP_TEST_ENV_SHOULD_BE_MISSING]
        ---
        # Epsilon
        Body of epsilon.
        """)

    # thai/emoji skill — UTF-8 round-trip (Feature: locale-independent stdout)
    t = os.path.join(root, "thai-skill")
    os.makedirs(t)
    w(os.path.join(t, "SKILL.md"), """\
        ---
        name: thai-skill
        description: ทักษะภาษาไทย
        ---
        # ไทย
        เนื้อหาภาษาไทย พร้อมอิโมจิ ✅🔥
        """)

    # oversized reference file inside alpha -> must be refused (OOM guard)
    with open(os.path.join(a, "references", "big.bin"), "w") as f:
        f.write("x" * 1_100_000)

    # skill whose SKILL.md is itself a SYMLINK -> must still load (follow=True on
    # the trusted read; regression finding 4/5).
    realmd = os.path.join(os.path.dirname(root), "real-linked-SKILL.md")
    w(realmd, """\
        ---
        name: linked-skill
        description: loaded via a symlinked SKILL.md
        ---
        # Linked
        Body via symlink.
        """)
    ls = os.path.join(root, "linked-skill")
    os.makedirs(ls)
    os.symlink(realmd, os.path.join(ls, "SKILL.md"))

    os.makedirs(os.path.join(root, "not-a-skill"))
    w(os.path.join(root, "not-a-skill", "README.md"), "ignore me\n")
    w(os.path.join(os.path.dirname(root), "SECRET.txt"), "top secret\n")


class Server:
    def __init__(self, skills_dir):
        env = dict(os.environ, SKILLS_MCP_DIR=skills_dir)
        self.p = subprocess.Popen(
            [sys.executable, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=env, text=True, bufsize=1,
        )

    def call(self, obj):
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()
        if "id" not in obj:
            return None
        return json.loads(self.p.stdout.readline())

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)


def call_tool(srv, mid, name, args):
    r = srv.call({"jsonrpc": "2.0", "id": mid, "method": "tools/call",
                  "params": {"name": name, "arguments": args}})
    result = r.get("result", {})
    text = result["content"][0]["text"]
    return result, (json.loads(text) if not result.get("isError") else text)


def make_retrieve_fixture(root):
    """A catalog deliberately larger than FULL_DUMP_MAX, with three skills whose
    wording is distinctive enough that a correct BM25 must rank them first."""
    def skill(name, desc, extra="", body="Body text.\n"):
        d = os.path.join(root, name)
        os.makedirs(d)
        w(os.path.join(d, "SKILL.md"), f"---\nname: {name}\ndescription: {desc}\n{extra}---\n\n{body}")

    skill("tmux-enter-swallow",
          "Fix a tmux pane that swallows the Enter key when text and submit are sent together.")
    skill("azure-deploy-proof",
          "Prove an Azure App Service deployment actually landed when the platform reports success.")
    skill("hunk-staging",
          "Stage only your own hunks when the working tree holds unrelated uncommitted WIP.")
    skill("gated-postgres", "Inspect a postgres database schema and its indexes.",
          extra="requires:\n  tools:\n    - PostgresQuery\n")
    for i in range(45):  # filler: push the catalog past FULL_DUMP_MAX
        skill(f"filler-{i:02d}", f"Placeholder capability number {i} for catalog sizing.")


def test_retrieve():
    """RETRIEVE wired into skills_list: ranked query, compact dump, gates."""
    with tempfile.TemporaryDirectory() as tmp:
        root = os.path.join(tmp, "skills")
        os.makedirs(root)
        make_retrieve_fixture(root)
        srv = Server(root)
        try:
            srv.call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "t", "version": "0"}}})

            _, big = call_tool(srv, 2, "skills_list", {"agent_tools": ["Bash"]})
            check("no query + big catalog -> compact mode", big.get("mode") == "compact")
            check("compact omits descriptions",
                  all("description" not in s for s in big["skills"]))
            check("compact still names every visible skill", big["count"] == 48)
            check("compact tells the model to use query", "query=" in big.get("note", ""))

            _, hit = call_tool(srv, 3, "skills_list",
                               {"query": "tmux pane swallows the enter key", "agent_tools": ["Bash"]})
            check("query ranks the right skill first",
                  hit["skills"][0]["name"] == "tmux-enter-swallow")
            check("ranked hits carry matched_by", hit["skills"][0]["matched_by"] == "bm25")
            check("ranked hits carry a score", isinstance(hit["skills"][0]["score"], (int, float)))
            check("ranked hits carry descriptions", "description" in hit["skills"][0])
            check("query reports how many were searched", hit["searched"] == 48)
            # BM25 only returns documents sharing a term, so k is a ceiling, not a
            # floor: a narrow query must NOT be padded out to k with noise.
            check("narrow query returns only real matches, not k of them",
                  0 < hit["count"] < 8)
            _, broad = call_tool(srv, 12, "skills_list",
                                 {"query": "placeholder capability number", "agent_tools": ["Bash"]})
            check("broad query is capped at k, not the whole catalog", broad["count"] == 8)

            _, dep = call_tool(srv, 4, "skills_list",
                               {"query": "prove the deployment really landed", "agent_tools": ["Bash"]})
            check("second query ranks its own skill first",
                  dep["skills"][0]["name"] == "azure-deploy-proof")

            _, exact = call_tool(srv, 5, "skills_list",
                                 {"query": "hunk-staging", "agent_tools": ["Bash"]})
            check("exact name hits the name-exact layer",
                  exact["skills"][0]["matched_by"] == "name-exact")

            _, junk = call_tool(srv, 6, "skills_list", {"query": "??? ...", "agent_tools": ["Bash"]})
            check("unsearchable query returns 0, not everything", junk["count"] == 0)
            check("unsearchable query explains itself", "No searchable terms" in junk["note"])

            _, pin = call_tool(srv, 7, "skills_list",
                               {"query": "placeholder", "k": 3, "pinned": ["hunk-staging"],
                                "agent_tools": ["Bash"]})
            check("pinned comes first", pin["skills"][0]["name"] == "hunk-staging")
            check("pinned is labelled", pin["skills"][0]["matched_by"] == "pinned")
            check("pinned needs no query match", pin["skills"][0]["score"] is None)
            check("k caps pinned + ranked together", pin["count"] == 3)

            _, clamp = call_tool(srv, 8, "skills_list", {"query": "placeholder", "k": 9999,
                                                         "agent_tools": ["Bash"]})
            check("k is clamped, cannot dump the catalog", clamp["k"] == 25)

            _, gated = call_tool(srv, 9, "skills_list",
                                 {"query": "postgres database schema indexes",
                                  "agent_tools": ["Bash"]})
            check("a tool-gated skill cannot surface through search",
                  all(s["name"] != "gated-postgres" for s in gated["skills"]))
            _, ungated = call_tool(srv, 10, "skills_list",
                                   {"query": "postgres database schema indexes",
                                    "agent_tools": ["Bash", "PostgresQuery"]})
            check("the same skill surfaces once its tool is available",
                  ungated["skills"][0]["name"] == "gated-postgres")

            _, cat = call_tool(srv, 11, "skills_list",
                               {"category": "nope", "agent_tools": ["Bash"]})
            check("category filter still applies", cat["count"] == 0)
        finally:
            srv.close()

    with tempfile.TemporaryDirectory() as tmp:  # small catalog keeps the old behavior
        root = os.path.join(tmp, "skills")
        os.makedirs(root)
        make_fixture(root)
        srv = Server(root)
        try:
            srv.call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                 "clientInfo": {"name": "t", "version": "0"}}})
            _, small = call_tool(srv, 2, "skills_list", {"agent_tools": ["Bash"]})
            check("small catalog still full-dumps", small.get("mode") is None)
            check("small catalog keeps descriptions",
                  any("description" in s for s in small["skills"]))
        finally:
            srv.close()


def test_hook():
    """Feature 4 Channel C: hook injects agent_tools into a skills_list call."""
    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "mcp__skills__skills_list",
        "tool_input": {"category": "x"},
        "transcript_path": "/nonexistent",
    }
    out = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                         capture_output=True, text=True)
    data = json.loads(out.stdout)
    inj = data["hookSpecificOutput"]["updatedInput"]
    check("hook preserves existing args", inj.get("category") == "x")
    check("hook injects agent_tools with builtins", "Bash" in inj["agent_tools"])

    # non-matching tool -> no output
    other = subprocess.run([sys.executable, HOOK],
                           input=json.dumps({"tool_name": "Bash", "tool_input": {}}),
                           capture_output=True, text=True)
    check("hook ignores non-skills_list tools", other.stdout.strip() == "")


def main():
    with tempfile.TemporaryDirectory() as tmp:
        skills = os.path.join(tmp, "skills")
        os.makedirs(skills)
        make_fixture(skills)
        srv = Server(skills)
        try:
            init = srv.call({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                             "params": {"protocolVersion": "2025-06-18"}})
            check("initialize returns serverInfo", init["result"]["serverInfo"]["name"] == "skills")
            check("initialize echoes protocolVersion", init["result"]["protocolVersion"] == "2025-06-18")

            check("initialized notification -> no reply",
                  srv.call({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None)

            tl = srv.call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
            names = {t["name"] for t in tl["result"]["tools"]}
            check("tools/list has all 3 tools", names == {"skills_list", "skill_view", "skill_patch"})

            # ── Feature 1: discovery ──
            _, cat = call_tool(srv, 3, "skills_list", {"all": True})
            got = {s["name"] for s in cat["skills"]}
            check("skills_list(all) finds every skill, ignores non-skill dir",
                  got == {"alpha-skill", "beta-skill", "gamma-skill", "delta-skill",
                          "epsilon-skill", "thai-skill", "linked-skill"})
            _, lv = call_tool(srv, 100, "skill_view", {"name": "linked-skill"})
            check("symlinked SKILL.md still loads (follow=True)",
                  not isinstance(lv, str) and "Body via symlink" in lv["content"])
            beta = next(s for s in cat["skills"] if s["name"] == "beta-skill")
            check("colon in description parsed", beta["description"].endswith("a colon: here."))

            _, filt = call_tool(srv, 4, "skills_list", {"category": "testing", "all": True})
            check("category filter works", [s["name"] for s in filt["skills"]] == ["alpha-skill"])

            # ── Feature 4: conditional visibility ──
            _, deflist = call_tool(srv, 5, "skills_list", {})
            shown = {s["name"] for s in deflist["skills"]}
            check("default hides skill needing unregistered MCP server",
                  "gamma-skill" not in shown)
            check("hidden_count reported", deflist.get("hidden_count", 0) >= 1)
            check("no agent_tools -> tool-gated skill still shown (delta) + hint",
                  "delta-skill" in shown and "_hint" in deflist)

            _, withtools = call_tool(srv, 6, "skills_list", {"agent_tools": []})
            check("agent_tools=[] hides skill needing FooTool",
                  "delta-skill" not in {s["name"] for s in withtools["skills"]})
            _, withfoo = call_tool(srv, 7, "skills_list", {"agent_tools": ["FooTool"]})
            check("agent_tools=[FooTool] reveals delta",
                  "delta-skill" in {s["name"] for s in withfoo["skills"]})

            _, alllist = call_tool(srv, 8, "skills_list", {"all": True})
            check("all=true shows gamma despite missing server",
                  "gamma-skill" in {s["name"] for s in alllist["skills"]})

            # ── Feature 3: per-file references ──
            _, av = call_tool(srv, 9, "skill_view", {"name": "alpha-skill"})
            check("skill_view body", "Body of alpha" in av["content"])
            check("skill_view strips frontmatter", "content_hash:" not in av["content"])
            check("skill_view surfaces linked file", "references/detail.md" in av["linked_files"])
            _, ref = call_tool(srv, 10, "skill_view",
                               {"name": "alpha-skill", "file_path": "references/detail.md"})
            check("skill_view loads reference on demand", "Deep alpha reference" in ref["content"])

            # ── Feature 2: readiness ──
            check("skill_view alpha readiness available", av["readiness"]["status"] == "available")
            _, ev = call_tool(srv, 11, "skill_view", {"name": "epsilon-skill"})
            check("readiness flags missing command",
                  "definitely-not-a-real-binary-xyz" in (ev["readiness"]["missing"] or {}).get("commands", []))
            check("readiness flags missing env",
                  "SKILLS_MCP_TEST_ENV_SHOULD_BE_MISSING" in (ev["readiness"]["missing"] or {}).get("env", []))
            check("readiness status setup_needed", ev["readiness"]["status"] == "setup_needed")

            # ── security ──
            res, _ = call_tool(srv, 12, "skill_view",
                               {"name": "alpha-skill", "file_path": "../../SECRET.txt"})
            check("path traversal (..) refused", res.get("isError") is True)
            res2, _ = call_tool(srv, 13, "skill_view",
                                {"name": "alpha-skill", "file_path": "/etc/passwd"})
            check("absolute path refused", res2.get("isError") is True)
            res3, _ = call_tool(srv, 14, "skill_view", {"name": "ghost"})
            check("unknown skill errors cleanly", res3.get("isError") is True)

            # ── Feature 5: skill_patch ──
            res5, patch = call_tool(srv, 15, "skill_patch",
                                    {"name": "alpha-skill",
                                     "old_string": "OLD_COMMAND --flag",
                                     "new_string": "NEW_COMMAND --flag",
                                     "edited_by": "tester"})
            check("skill_patch succeeds", not res5.get("isError") and patch["patched"])
            check("skill_patch reports edited_by", patch["edited_by"] == "tester")
            # verify on disk
            with open(os.path.join(skills, "alpha-skill", "SKILL.md")) as f:
                disk = f.read()
            check("patch applied to body", "NEW_COMMAND --flag" in disk and "OLD_COMMAND" not in disk)
            check("patch re-stamped content_hash (not deadbeef)",
                  "content_hash: deadbeef" not in disk and "content_hash:" in disk)
            check("patch stamped edited_by", "edited_by: tester" in disk)
            # frontmatter of other keys preserved
            check("patch preserved other frontmatter", "category: testing" in disk)

            res6, err6 = call_tool(srv, 16, "skill_patch",
                                   {"name": "alpha-skill", "old_string": "NOPE", "new_string": "x"})
            check("patch missing old_string errors", res6.get("isError") is True)
            res7, err7 = call_tool(srv, 17, "skill_patch",
                                   {"name": "beta-skill", "old_string": "o", "new_string": "0"})
            check("patch non-unique old_string errors", res7.get("isError") is True)

            # regression 1: edited_by newline injection must NOT hijack identity
            call_tool(srv, 30, "skill_patch",
                      {"name": "alpha-skill", "old_string": "NEW_COMMAND --flag",
                       "new_string": "NEWER --flag", "edited_by": "me\nname: victim-skill\n---\nx"})
            _, after = call_tool(srv, 31, "skills_list", {"all": True})
            afternames = {s["name"] for s in after["skills"]}
            check("newline-injection does NOT create victim skill", "victim-skill" not in afternames)
            check("newline-injection does NOT lose alpha identity", "alpha-skill" in afternames)
            with open(os.path.join(skills, "alpha-skill", "SKILL.md")) as f:
                adisk = f.read()
            check("no injected 'name: victim' frontmatter line",
                  "\nname: victim-skill" not in adisk)

            # regression 2/3: pre-planted SKILL.md.tmp symlink must not be written through
            outside = os.path.join(tmp, "OUTSIDE_SECRET.txt")
            w(outside, "safe")
            alpha_md = os.path.join(skills, "alpha-skill", "SKILL.md")
            os.symlink(outside, os.path.join(skills, "alpha-skill", "SKILL.md.tmp"))
            call_tool(srv, 32, "skill_patch",
                      {"name": "alpha-skill", "old_string": "NEWER --flag", "new_string": "N3 --flag"})
            with open(outside) as f:
                check("tmp-symlink attack: outside file untouched", f.read() == "safe")
            check("tmp-symlink attack: SKILL.md not turned into a symlink",
                  not os.path.islink(alpha_md))

            # ── Feature 10/12: UTF-8 + size cap ──
            _, tv = call_tool(srv, 18, "skill_view", {"name": "thai-skill"})
            check("UTF-8 Thai body round-trips", "เนื้อหาภาษาไทย" in tv["content"])
            check("emoji round-trips", "✅🔥" in tv["content"])
            bigres, bigmsg = call_tool(srv, 19, "skill_view",
                                       {"name": "alpha-skill", "file_path": "references/big.bin"})
            check("oversize file refused (OOM guard)", bigres.get("isError") is True)
            check("size-cap error leaks no absolute path",
                  isinstance(bigmsg, str) and "/home/" not in bigmsg and "too large" in bigmsg)

            # ── protocol robustness ──
            um = srv.call({"jsonrpc": "2.0", "id": 20, "method": "does/not/exist"})
            check("unknown method -> -32601", um["error"]["code"] == -32601)

            # protocolVersion negotiation: unsupported -> server returns a supported one
            badinit = srv.call({"jsonrpc": "2.0", "id": 21, "method": "initialize",
                                "params": {"protocolVersion": "1999-01-01"}})
            check("unsupported protocolVersion negotiated down",
                  badinit["result"]["protocolVersion"] != "1999-01-01")

            # id present-but-null
            idnull = srv.call({"jsonrpc": "2.0", "id": None, "method": "ping"})
            check("id=null handled", idnull["id"] is None and idnull["result"] == {})

            # batch array -> -32600, server survives
            srv.p.stdin.write(json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]) + "\n")
            srv.p.stdin.flush()
            batch = json.loads(srv.p.stdout.readline())
            check("batch array -> -32600 (not a crash)", batch["error"]["code"] == -32600)

            # bare scalar -> -32600
            srv.p.stdin.write("42\n")
            srv.p.stdin.flush()
            scal = json.loads(srv.p.stdout.readline())
            check("bare scalar -> -32600", scal["error"]["code"] == -32600)

            srv.p.stdin.write("{ not json\n")
            srv.p.stdin.flush()
            pe = json.loads(srv.p.stdout.readline())
            check("malformed line -> -32700, survives", pe["error"]["code"] == -32700)
            check("id=0 handled (falsy id)",
                  srv.call({"jsonrpc": "2.0", "id": 0, "method": "ping"})["id"] == 0)
        finally:
            srv.close()

    test_retrieve()
    test_hook()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
