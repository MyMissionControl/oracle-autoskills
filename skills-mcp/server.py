#!/usr/bin/env python3
"""skills-mcp — a lazy skill librarian over stdio (MCP JSON-RPC 2.0).

Why this exists — REVISED 2026-08-07
------------------------------------
It was built to move the skill catalog OFF the always-on system prompt and INTO
tool responses, replacing Claude Code's eager listing with a BM25 search. That
goal was retired. Measured on this machine: the listing is 57.7 tokens/skill
against the agentskills.io figure of ~100, it resolves at t0 into a 96.8%
cache-read prefix before the model's first token, and it carried 358 Skill()
invocations against 3 skills_list calls. A search can only run after the model
has already decided, is billed uncached, and must discard candidates the listing
already showed. The ranker is gone; see the note above BUILTIN_TOOLS.

What remains is a librarian that complements the listing instead of competing
with it:
  1. catalog listing ..... skills_list()  — name+description, alphabetical.
                           Its real job is reading back a description that
                           skillOverrides suppressed to `name-only`.
  2. readiness gating .... skill_view() reports missing env/commands/files/mcp
  3. per-file references .. skill_view(name, file_path)
  4. conditional vis. .... skills_list(agent_tools=...) hides unrunnable skills;
                           mcp requirements checked server-side from config
  5. skill repair ........ skill_patch(name, old_string, new_string) re-stamps
                           content_hash + edited_by/at provenance

Design constraints
  - stdlib + PyYAML only. stdout carries ONLY newline-delimited JSON-RPC;
    logs go to stderr. path-traversal safe on skill_view(file_path).
"""

from __future__ import annotations

import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from typing import Any

SERVER_NAME = "skills"
# Bump on every deployed change. 0.3.0 shipped without BUILD/RETRIEVE, and an
# undeployed rewrite carrying the same string made the two indistinguishable
# from the outside — the version is the only handle a caller has on which build
# is actually running.
SERVER_VERSION = "0.4.0"
DEFAULT_PROTOCOL_VERSION = "2025-06-18"
# Versions we actually implement. Negotiate against these instead of echoing
# whatever the client asks for (MCP requires responding with a supported one).
SUPPORTED_PROTOCOL_VERSIONS = {"2025-06-18", "2025-03-26", "2024-11-05"}

# Hard cap on any single file we read into memory + serialize. This host guards
# against OOM (earlyoom + cgroup caps); a planted multi-GB file must not be able
# to materialize here. Skills are tiny; 1 MB is generous.
MAX_FILE_BYTES = 1_000_000

def _split_roots(raw: str) -> list[str]:
    out: list[str] = []
    for part in raw.split(os.pathsep):
        part = part.strip()
        if not part:
            continue
        p = os.path.abspath(os.path.expanduser(part))
        if p not in out:
            out.append(p)
    return out


# Skill roots in PRECEDENCE order: an earlier root shadows a later one on a
# duplicate skill name (spec 2.2 "first root wins — local shadows external").
#   SKILLS_MCP_ROOTS  colon-separated list  -> authoritative
#   SKILLS_MCP_DIR    single dir            -> stays single-root on purpose, so
#                                              an explicit dir never silently
#                                              picks up other roots (tests rely
#                                              on this)
_ENV_ROOTS = os.environ.get("SKILLS_MCP_ROOTS", "").strip()
_ENV_DIR = os.environ.get("SKILLS_MCP_DIR", "").strip()
if _ENV_ROOTS:
    SKILL_ROOTS = _split_roots(_ENV_ROOTS)
elif _ENV_DIR:
    SKILL_ROOTS = _split_roots(_ENV_DIR)
else:
    SKILL_ROOTS = _split_roots(f"~/.claude/skills-lib{os.pathsep}~/.claude/skills")

# Kept for output/logging compatibility: the primary (highest-precedence) root.
SKILLS_DIR = SKILL_ROOTS[0] if SKILL_ROOTS else os.path.expanduser("~/.claude/skills")

# RETRIEVAL WAS REMOVED 2026-08-07. What used to live here — FULL_DUMP_MAX,
# DEFAULT_K, MAX_K, SKILLS_INDEX_NO_BODY and the BM25 FIELD_WEIGHTS — existed to
# rank the catalog against a query. It was retired for one structural reason:
# Claude Code already injects every skill's name and description into the system
# prompt at t0, before the model's first token, as stage 1 of the agentskills.io
# progressive-disclosure spec. A ranker can only run after that, must discard
# candidates the listing already showed, and measured 42% acc@1 against a
# mechanism that cannot miss. 358 Skill() invocations rode on the listing against
# 3 skills_list calls in eight weeks.
#
# skills_list is now what Hermes ships: a plain catalog listing, optional
# category filter, stable order, no query parameter.

# Built-in Claude Code tools — always present, so requires.tools on these is
# satisfiable without the agent reporting them.
BUILTIN_TOOLS = {
    "Bash", "Read", "Edit", "Write", "Glob", "Grep", "LS", "List",
    "WebFetch", "WebSearch", "Task", "Agent", "TodoWrite", "NotebookEdit",
    "Skill", "MultiEdit", "ExitPlanMode",
}


def log(*a: Any) -> None:
    print("[skills-mcp]", *a, file=sys.stderr, flush=True)


# ── frontmatter ──────────────────────────────────────────────────────────────
def _split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Thin wrapper over _split_frontmatter_ex
    for callers that do not care how the parse went."""
    fm, body, _status = _split_frontmatter_ex(text)
    return fm, body


def _split_frontmatter_ex(text: str) -> tuple[dict, str, str | None]:
    """Return (frontmatter_dict, body, status). PyYAML for nested blocks (e.g.
    requires:), with a dependency-free flat fallback for top-level keys.

    `status` is None on a clean parse, else a short reason. Hermes silently falls
    back to naive `key: value` splitting when YAML fails, which admits a skill
    whose metadata is quietly wrong; we keep the fallback (it is legitimate when
    PyYAML is absent) but make the degradation REPORTABLE instead of invisible.
    We do not exclude on it: Claude Code parses frontmatter with its own parser,
    so a file PyYAML dislikes may still be a working skill there — dropping it
    here would desync our index from the CLI's listing."""
    if not text.startswith("---"):
        return {}, text, "no frontmatter fence"
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text, "frontmatter fence never closes"
    fm_block = "\n".join(lines[1:end])
    body = "\n".join(lines[end + 1:]).lstrip("\n")

    status: str | None = None
    try:
        import yaml  # type: ignore
    except Exception:
        status = "PyYAML unavailable; parsed with the flat fallback"
    else:
        try:
            parsed = yaml.safe_load(fm_block)
        except Exception as e:
            status = f"YAML parse error, used flat fallback: {str(e).splitlines()[0][:120]}"
        else:
            if isinstance(parsed, dict):
                return {str(k): v for k, v in parsed.items()}, body, None
            status = f"frontmatter is not a mapping ({type(parsed).__name__}); used flat fallback"

    fm: dict = {}
    for raw in fm_block.splitlines():
        if not raw.strip() or raw.lstrip() != raw:
            continue
        if ":" not in raw:
            continue
        key, _, val = raw.partition(":")
        key, val = key.strip(), val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            quote, val = val[0], val[1:-1]
            if quote == "'":
                val = val.replace("''", "'")  # YAML single-quote escaping
        fm[key] = val
    return fm, body, status


def _raw_frontmatter(text: str) -> tuple[list[str], str]:
    """Return (frontmatter_lines_without_markers, body) from raw SKILL.md text.
    Used by skill_patch to edit in place while preserving key order/format."""
    if not text.startswith("---"):
        return [], text
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return [], text
    return lines[1:end], "\n".join(lines[end + 1:]).lstrip("\n")


def _set_fm_key(fm_lines: list[str], key: str, value: str) -> list[str]:
    """Replace `key: ...` in place, else append it. Only touches top-level keys.
    Newlines/CRs in the value are flattened so a caller-supplied value can never
    inject extra frontmatter lines (e.g. a second `name:` or a premature '---')."""
    value = str(value).replace("\n", " ").replace("\r", " ")
    out = []
    replaced = False
    for ln in fm_lines:
        stripped = ln.strip()
        if stripped == ln and (stripped == f"{key}:" or stripped.startswith(f"{key}:")):
            out.append(f"{key}: {value}")
            replaced = True
        else:
            out.append(ln)
    if not replaced:
        out.append(f"{key}: {value}")
    return out


def _body_hash(body: str) -> str:
    """Matches auto_skill.py::_body_hash so patched skills stay consistent."""
    return hashlib.sha256(body.strip().encode("utf-8")).hexdigest()


def _now_iso() -> str:
    try:
        return datetime.datetime.now().astimezone().replace(microsecond=0).isoformat()
    except Exception:
        return datetime.datetime.now().replace(microsecond=0).isoformat()


def _read_text_capped(path: str, follow: bool = False) -> str:
    """Read a file as UTF-8 with a hard size cap (OOM guard). By default opens
    O_NOFOLLOW on the final component to close the TOCTOU symlink-swap window on
    UNTRUSTED reference-file reads (post _safe_join). For the TRUSTED SKILL.md
    read, pass follow=True: a skill legitimately installed as a symlinked file
    (or under a symlinked dir) must still load. OSErrors are sanitized to a
    generic ValueError so absolute paths never leak into tool output."""
    flags = os.O_RDONLY
    if not follow:
        flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as e:
        log("open failed:", path, e)
        raise ValueError("could not read the requested file")
    try:
        size = os.fstat(fd).st_size
        if size > MAX_FILE_BYTES:
            raise ValueError(
                f"file too large ({size} bytes; cap is {MAX_FILE_BYTES})"
            )
        data = os.read(fd, MAX_FILE_BYTES + 1)
    except OSError as e:
        log("read failed:", path, e)
        raise ValueError("could not read the requested file")
    finally:
        os.close(fd)
    if len(data) > MAX_FILE_BYTES:
        raise ValueError(f"file too large (>{MAX_FILE_BYTES} bytes)")
    return data.decode("utf-8", errors="replace")


def _skill_name(fm: dict, dir_name: str) -> str:
    """Canonical skill identity — the SAME rule load_catalog advertises, so
    skill_view resolves exactly what skills_list listed (no name/dir mismatch)."""
    return str(fm.get("name") or dir_name).strip()


# ── skill discovery + BUILD ──────────────────────────────────────────────────
def _as_dict(v: Any) -> dict:
    return v if isinstance(v, dict) else {}


def _as_list(v: Any) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


_PLATFORM_ALIASES = {
    "darwin": "macos", "osx": "macos", "mac": "macos", "macos": "macos",
    "linux": "linux", "win32": "windows", "windows": "windows",
}


def _os_tag() -> str:
    p = sys.platform
    if p.startswith("linux"):
        return "linux"
    if p == "darwin":
        return "macos"
    if p.startswith("win"):
        return "windows"
    return p


def _iter_skill_dirs():
    """Yield (root, skill_dir, skill_md) across every configured root, in
    precedence order (an earlier root shadows a later one on a duplicate name)."""
    for root in SKILL_ROOTS:
        for md in sorted(glob.glob(os.path.join(root, "*", "SKILL.md"))):
            yield root, os.path.dirname(md), md


# (path, mtime_ns, size) -> parsed entry. Spec 3.1 says do NOT persist an index
# to disk ("a stale index is a worse problem than a fast rescan"); this is only a
# per-process memo so repeated calls in one session skip re-reading every body.
_ENTRY_CACHE: dict[tuple, dict] = {}
_ENTRY_CACHE_MAX = 2_000


def _parse_entry(root: str, skill_dir: str, md: str) -> tuple[dict | None, str | None]:
    """Return (entry, None) or (None, exclusion_reason). Never raises: a broken
    skill must not take the session down (spec invariant 5)."""
    try:
        st = os.stat(md)
    except OSError:
        return None, "SKILL.md could not be stat'd"
    key = (md, st.st_mtime_ns, st.st_size)
    hit = _ENTRY_CACHE.get(key)
    if hit is not None:
        return dict(hit), None

    try:
        text = _read_text_capped(md, follow=True)
    except ValueError as e:
        return None, str(e)

    fm, body, fm_status = _split_frontmatter_ex(text)
    dir_name = os.path.basename(skill_dir)
    name = _skill_name(fm, dir_name)
    if not name:
        return None, "missing 'name' and no usable directory name"
    # A missing description is NOT an exclusion here, unlike spec 2.2. That rule
    # is written for an index whose only surface is the description; ours also
    # indexes the name and the whole body, so an undescribed skill stays both
    # searchable and viewable. Excluding it would hide a skill the user uploaded
    # by hand -- the common reason a description is absent. It simply lists as a
    # bare name, which is what the eager listing does with it anyway.
    desc = str(fm.get("description") or "").strip() or None

    plats = [
        _PLATFORM_ALIASES.get(str(p).strip().lower(), str(p).strip().lower())
        for p in _as_list(fm.get("platforms"))
    ]
    if plats and _os_tag() not in plats:
        return None, f"platform gate: declares {'/'.join(plats)}, host is {_os_tag()}"

    entry = {
        "name": name,
        "description": desc,
        "category": str(fm.get("category") or "").strip() or None,
        "trigger": str(fm.get("trigger") or "").strip() or None,
        "_requires": _as_dict(fm.get("requires")),
        "_dir": dir_name,
        "_root": root,
        "_path": md,
        # `_triggers` and `_body` used to be indexed here as retrieval surface.
        # With the ranker gone nothing consumes them, and reading every body on
        # every index build was pure cost, so they are no longer carried.
    }
    if len(_ENTRY_CACHE) > _ENTRY_CACHE_MAX:
        _ENTRY_CACHE.clear()
    _ENTRY_CACHE[key] = dict(entry)
    return dict(entry), None


def build_index() -> tuple[list[dict], list[dict]]:
    """BUILD stage. Returns (entries, excluded); every exclusion carries a reason
    (spec invariant 4 — silent filtering is undebuggable)."""
    entries: list[dict] = []
    excluded: list[dict] = []
    seen: dict[str, str] = {}
    for root, skill_dir, md in _iter_skill_dirs():
        entry, reason = _parse_entry(root, skill_dir, md)
        if entry is None:
            excluded.append({
                "skill": os.path.basename(skill_dir), "root": root, "reason": reason,
            })
            log("exclude", md, "-", reason)
            continue
        prev_root = seen.get(entry["name"])
        if prev_root is not None:
            excluded.append({
                "skill": entry["name"], "root": root,
                "reason": f"shadowed: name already provided by higher-precedence root {prev_root}",
            })
            log("duplicate skill name, keeping first:", entry["name"])
            continue
        seen[entry["name"]] = root
        entries.append(entry)
    return entries, excluded


def load_catalog() -> list[dict]:
    """Back-compat wrapper — entries only."""
    return build_index()[0]


def _resolve_skill_dir(name: str) -> str | None:
    """Resolve through the SAME index skills_list advertises, so skill_view can
    never land on a skill the catalog excluded, nor on a lower-precedence root's
    copy of a shadowed name."""
    for e in build_index()[0]:
        if e["name"] == name:
            return os.path.dirname(e["_path"])
    return None


def _linked_files(skill_dir: str) -> list[str]:
    out = []
    real_root = os.path.realpath(skill_dir)
    for root, _dirs, files in os.walk(real_root):
        for fn in files:
            rel = os.path.relpath(os.path.join(root, fn), real_root)
            if rel != "SKILL.md":
                out.append(rel)
    return sorted(out)


def _safe_join(skill_dir: str, file_path: str) -> str | None:
    real_root = os.path.realpath(skill_dir)
    if os.path.isabs(file_path):
        return None
    candidate = os.path.realpath(os.path.join(real_root, file_path))
    if candidate == real_root:
        return None
    if os.path.commonpath([real_root, candidate]) != real_root:
        return None
    if not os.path.isfile(candidate):
        return None
    return candidate


# ── requirements: readiness (#2) + visibility (#4) ───────────────────────────
def registered_mcp_servers() -> set[str]:
    """Union of MCP servers registered in ~/.claude.json (global + all projects)
    and ./.mcp.json. Over-approximates 'registered' so we only ever HIDE a skill
    when its server is DEFINITELY absent."""
    servers: set[str] = set()

    def add_from(d: dict):
        for k in _as_dict(d.get("mcpServers")):
            servers.add(k)

    try:
        with open(os.path.expanduser("~/.claude.json"), "r", encoding="utf-8") as f:
            top = json.load(f)
        add_from(top)
        for _proj, cfg in _as_dict(top.get("projects")).items():
            add_from(_as_dict(cfg))
    except (OSError, json.JSONDecodeError) as e:
        log("registered_mcp_servers: ~/.claude.json", e)

    try:
        with open(os.path.join(os.getcwd(), ".mcp.json"), "r", encoding="utf-8") as f:
            add_from(json.load(f))
    except (OSError, json.JSONDecodeError):
        pass
    return servers


def _readiness(requires: dict) -> dict:
    """Feature 2: report machine-checkable prerequisites (env/commands/files/mcp)."""
    requires = _as_dict(requires)
    missing = {}
    miss_env = [e for e in _as_list(requires.get("env")) if not os.environ.get(str(e))]
    if miss_env:
        missing["env"] = miss_env
    miss_cmd = [c for c in _as_list(requires.get("commands")) if shutil.which(str(c)) is None]
    if miss_cmd:
        missing["commands"] = miss_cmd
    miss_file = [
        f for f in _as_list(requires.get("files"))
        if not os.path.exists(os.path.expanduser(str(f)))
    ]
    if miss_file:
        missing["files"] = miss_file
    reg = registered_mcp_servers()
    miss_mcp = [m for m in _as_list(requires.get("mcp")) if str(m) not in reg]
    if miss_mcp:
        missing["mcp"] = miss_mcp

    required_tools = [str(t) for t in _as_list(requires.get("tools"))]
    out = {
        "status": "setup_needed" if missing else "available",
        "missing": missing or None,
    }
    if required_tools:
        # Can't verify agent tools at view-time (process isolation) — report them.
        out["required_tools"] = required_tools
    return out


def _visibility_hide_reason(requires: dict, agent_tools, agent_toolsets) -> str | None:
    """Feature 4: reason to HIDE a skill, or None to show it.
    - mcp: server-side certain (config).
    - tools/toolsets: only decidable when the agent's inventory is known."""
    requires = _as_dict(requires)
    reg = registered_mcp_servers()
    miss_mcp = [m for m in _as_list(requires.get("mcp")) if str(m) not in reg]
    if miss_mcp:
        return f"requires MCP server(s) not registered: {', '.join(map(str, miss_mcp))}"

    req_tools = [str(t) for t in _as_list(requires.get("tools"))]
    if req_tools and agent_tools is not None:
        avail = set(map(str, agent_tools)) | BUILTIN_TOOLS
        miss = [t for t in req_tools if t not in avail]
        if miss:
            return f"requires tool(s) unavailable: {', '.join(miss)}"

    req_ts = [str(t) for t in _as_list(requires.get("toolsets"))]
    if req_ts and agent_toolsets is not None:
        avail = set(map(str, agent_toolsets))
        miss = [t for t in req_ts if t not in avail]
        if miss:
            return f"requires toolset(s) unavailable: {', '.join(miss)}"
    return None


# ── tools ────────────────────────────────────────────────────────────────────
def _public_entry(entry: dict, extra: dict | None = None) -> dict:
    """The model-facing view of an index entry: no leading-underscore fields
    (spec 2.2 — path/triggers/body are retrieval surface, kept server-side)."""
    out = {key: val for key, val in entry.items()
           if not key.startswith("_") and val is not None}
    if extra:
        out.update(extra)
    return out


def tool_skills_list(args: dict) -> dict:
    """The plain catalog listing: name + description, optional category filter,
    stable alphabetical order. No query, no ranking, no k — see the note at the
    top of this file for why those were removed.

    Its remaining job is narrow and real: Claude Code's own listing suppresses
    the description of any skill set to `name-only` in skillOverrides, and this
    is how the model reads a suppressed one back without invoking the skill."""
    category = (args.get("category") or "").strip() or None
    agent_tools = args.get("agent_tools")
    agent_toolsets = args.get("agent_toolsets")
    show_all = bool(args.get("all"))

    catalog = load_catalog()
    if category:
        catalog = [c for c in catalog if (c.get("category") or "") == category]

    visible, hidden = [], 0
    for c in catalog:
        if not show_all:
            if _visibility_hide_reason(c.get("_requires"), agent_tools, agent_toolsets):
                hidden += 1
                continue
        visible.append(c)

    visible.sort(key=lambda c: (c.get("name") or ""))
    out: dict = {"skills_dir": SKILLS_DIR}
    out["count"] = len(visible)
    out["skills"] = [_public_entry(c) for c in visible]

    if hidden:
        out["hidden_count"] = hidden
        out["hidden_note"] = (
            f"{hidden} skill(s) hidden — required tools/servers unavailable. "
            "Call skills_list with all=true to see them."
        )
    if agent_tools is None:
        out["_hint"] = (
            "Tip: pass agent_tools=[...] (your available tool names) so skills "
            "needing tools you lack are hidden. Without it, tool-gated skills are shown."
        )
    return out


def tool_skill_view(args: dict) -> dict:
    name = (args.get("name") or "").strip()
    file_path = (args.get("file_path") or "").strip() or None
    if not name:
        raise ValueError("skill_view requires 'name'")
    skill_dir = _resolve_skill_dir(name)
    if not skill_dir:
        raise ValueError(f"skill not found: {name!r}")

    if file_path:
        resolved = _safe_join(skill_dir, file_path)
        if not resolved:
            raise ValueError(
                f"file_path {file_path!r} is invalid or escapes the skill directory"
            )
        # reference file is untrusted -> keep O_NOFOLLOW (default follow=False)
        return {"name": name, "file_path": file_path, "content": _read_text_capped(resolved)}

    md = os.path.join(skill_dir, "SKILL.md")
    fm, body = _split_frontmatter(_read_text_capped(md, follow=True))
    linked = _linked_files(skill_dir)
    return {
        "name": str(fm.get("name") or name),
        "description": str(fm.get("description") or ""),
        "content": body,
        "linked_files": linked or None,
        "usage_hint": (
            "To read a linked file, call skill_view(name, file_path) "
            "e.g. file_path='references/api.md'"
        ) if linked else None,
        "readiness": _readiness(fm.get("requires")),
    }


def tool_skill_patch(args: dict) -> dict:
    """Feature 5: targeted in-place edit of a skill body + re-stamp provenance.
    Body-only (frontmatter is the writer's domain); refuses non-unique matches."""
    name = (args.get("name") or "").strip()
    old_string = args.get("old_string")
    new_string = args.get("new_string")
    if not name:
        raise ValueError("skill_patch requires 'name'")
    if not old_string:
        raise ValueError("skill_patch requires a non-empty 'old_string'")
    if new_string is None:
        raise ValueError("skill_patch requires 'new_string'")
    if old_string == new_string:
        raise ValueError("old_string and new_string are identical")

    skill_dir = _resolve_skill_dir(name)
    if not skill_dir:
        raise ValueError(f"skill not found: {name!r}")
    md = os.path.join(skill_dir, "SKILL.md")
    fm_lines, body = _raw_frontmatter(_read_text_capped(md, follow=True))

    n = body.count(old_string)
    if n == 0:
        raise ValueError("old_string not found in skill body (patch edits the body only)")
    if n > 1:
        raise ValueError(f"old_string matches {n} places; add surrounding context to make it unique")

    new_body = body.replace(old_string, new_string, 1)
    source = (args.get("edited_by") or os.environ.get("AUTO_SKILL_SOURCE") or "skills-mcp").strip()
    # Collapse to a single line — a multi-line edited_by would otherwise inject
    # extra frontmatter lines (defense in depth; _set_fm_key also flattens).
    source = (source.splitlines()[0].strip() if source else "") or "skills-mcp"
    fm_lines = _set_fm_key(fm_lines, "content_hash", _body_hash(new_body))
    fm_lines = _set_fm_key(fm_lines, "edited_at", _now_iso())
    fm_lines = _set_fm_key(fm_lines, "edited_by", source)

    if fm_lines:
        new_text = "---\n" + "\n".join(fm_lines) + "\n---\n" + new_body
    else:
        new_text = new_body
    if not new_text.endswith("\n"):
        new_text += "\n"

    # Atomic write via an unpredictable, O_EXCL temp file in the same dir:
    # random name defeats a pre-planted SKILL.md.tmp symlink (arbitrary-write)
    # and cross-session tmp collisions; os.replace is the atomic swap.
    fd, tmp = tempfile.mkstemp(dir=skill_dir, prefix=".SKILL.md.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(new_text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, md)  # atomic
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return {
        "name": name,
        "patched": True,
        "content_hash": _body_hash(new_body),
        "edited_by": source,
        "body_chars": len(new_body),
    }


TOOLS = [
    {
        "name": "skills_list",
        "description": (
            "List the skill catalog: name + description, alphabetical. Your system "
            "prompt already carries this for every skill, so you rarely need it — "
            "the one case that matters is a skill shown to you as a bare NAME with "
            "no description (suppressed by skillOverrides): call this to read the "
            "description back, then skill_view for the full text. "
            "category filters; all=true shows skills hidden for missing tools."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional exact-match category filter."},
                "agent_tools": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Tool names you currently have available (for visibility filtering).",
                },
                "agent_toolsets": {
                    "type": "array", "items": {"type": "string"},
                    "description": "Toolset names you currently have available.",
                },
                "all": {"type": "boolean", "description": "Show skills that would otherwise be hidden."},
            },
        },
    },
    {
        "name": "skill_view",
        "description": (
            "Load a skill's full instructions by name, plus a readiness report "
            "(missing env vars / commands / files / MCP servers). Pass file_path "
            "to read one of the skill's linked reference files instead of the body."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill name to load."},
                "file_path": {"type": "string", "description": "Optional reference file, e.g. 'references/api.md'."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "skill_patch",
        "description": (
            "Repair a skill you loaded that had a wrong command, missing step, or "
            "a pitfall you discovered. Replaces old_string with new_string in the "
            "skill BODY (must match exactly once), then re-stamps content_hash and "
            "edited_by/edited_at provenance. Use after a task when a skill was wrong."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Skill to patch."},
                "old_string": {"type": "string", "description": "Exact text in the body to replace (must be unique)."},
                "new_string": {"type": "string", "description": "Replacement text."},
                "edited_by": {"type": "string", "description": "Who is patching (provenance); defaults to $AUTO_SKILL_SOURCE or 'skills-mcp'."},
            },
            "required": ["name", "old_string", "new_string"],
        },
    },
]

TOOL_IMPL = {
    "skills_list": tool_skills_list,
    "skill_view": tool_skill_view,
    "skill_patch": tool_skill_patch,
}


# ── JSON-RPC / MCP ───────────────────────────────────────────────────────────
def _result(msg_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    msg_id = msg.get("id")
    params = msg.get("params") or {}
    is_notification = "id" not in msg

    if method == "initialize":
        client_proto = params.get("protocolVersion")
        # Negotiate: only echo a version we actually implement, else our default.
        proto = client_proto if client_proto in SUPPORTED_PROTOCOL_VERSIONS else DEFAULT_PROTOCOL_VERSION
        return _result(msg_id, {
            "protocolVersion": proto,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method in ("notifications/initialized", "initialized"):
        return None

    if method == "ping":
        return _result(msg_id, {})

    if method == "tools/list":
        return _result(msg_id, {"tools": TOOLS})

    if method == "tools/call":
        tool_name = params.get("name")
        impl = TOOL_IMPL.get(tool_name)
        if impl is None:
            return _error(msg_id, -32602, f"unknown tool: {tool_name}")
        try:
            payload = impl(params.get("arguments") or {})
            text = json.dumps(payload, ensure_ascii=False, indent=2)
            return _result(msg_id, {"content": [{"type": "text", "text": text}]})
        except ValueError as e:
            # Our own, already-sanitized messages (no absolute paths).
            return _result(msg_id, {
                "content": [{"type": "text", "text": f"error: {e}"}],
                "isError": True,
            })
        except Exception as e:
            # Anything else (e.g. a stray OSError) may embed absolute paths —
            # log the detail to stderr, return a generic message.
            log("tool error:", tool_name, repr(e))
            return _result(msg_id, {
                "content": [{"type": "text", "text": "error: internal tool error"}],
                "isError": True,
            })

    if is_notification:
        return None
    return _error(msg_id, -32601, f"method not found: {method}")


def main() -> None:
    # Force UTF-8 on the protocol streams. Skill content is Thai/emoji-heavy;
    # under a C/POSIX locale the default codec would raise UnicodeEncodeError on
    # write and kill the server. Do this before any stdout write.
    try:
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
        sys.stdin.reconfigure(encoding="utf-8")
    except Exception as e:  # very old/odd streams — best effort
        log("stream reconfigure failed:", e)

    log(f"starting v{SERVER_VERSION}, SKILLS_DIR={SKILLS_DIR}")
    if not os.path.isdir(SKILLS_DIR):
        log(f"WARNING: skills dir does not exist: {SKILLS_DIR}")
    out = sys.stdout

    def emit(resp):
        try:
            out.write(json.dumps(resp, ensure_ascii=False) + "\n")
            out.flush()
        except UnicodeEncodeError:
            # last-ditch: escape non-ASCII rather than crash the loop
            out.write(json.dumps(resp) + "\n")
            out.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            emit(_error(None, -32700, f"parse error: {e}"))
            continue
        # JSON-RPC frame must be an object. Arrays (batch) and bare scalars would
        # crash handle()'s msg.get(...) — reject them cleanly and keep serving.
        if not isinstance(msg, dict):
            emit(_error(None, -32600, "invalid request: expected a JSON-RPC object"))
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            log("handler error:", repr(e))
            resp = _error(msg.get("id"), -32603, "internal error")
        if resp is not None:
            emit(resp)


if __name__ == "__main__":
    main()
