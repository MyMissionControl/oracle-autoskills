#!/usr/bin/env python3
"""bash_guard.py — PreToolUse(Bash) hook: block the two command shapes that FAIL SILENTLY on this box.

Both were hit for real by worker `jack` during the `agentskill-marketplace-newflow8` sprint 1 run
(2026-08-16), and both are invisible unless you already know the trap:

  1. `--screenshot=/tmp/...` — chromium here is a **snap**, which has its own private /tmp. The file
     is never written; chromium prints `Failed to write file … (2)` and exits 0-ish, so a loop over
     three viewports produces three errors and zero PNGs. Measured the same day: `/tmp/...` fails
     with ENOENT, a TOP-LEVEL `~/.hidden` path fails with EACCES, and a hidden dir nested inside a
     visible path (`<proj>/.orches-shots/...`) works — which is why the engine's own shots are fine.
  2. `pkill -f <pattern>` — the shell running the command has the whole command line in its own
     /proc cmdline, so the pattern matches the caller and pkill kills the command that issued it
     (observed: exit 144), often leaving the real server alive. The one-character fix is the
     bracket trick (`[n]ode src/index.js`), which cannot match itself.

⛔ Scope is deliberately narrow: **oracle sessions only** (repo dir ends in `-oracle`), the same test
`inject_rules.py` uses. A human's own shell is never touched. ⛔ Fail OPEN on anything unexpected —
a guard that blocks work because it crashed is worse than the bug it prevents.
"""
import json
import os
import re
import sys

ORACLE_SUFFIX = "-oracle"

SHOT_TMP = re.compile(r"--screenshot[= ]\"?'?(/tmp/\S*)")
PKILL_F = re.compile(r"\bpkill\s+(?:-\w+\s+)*-\w*f\w*\s+(\S+|\"[^\"]*\"|'[^']*')")


def _stdin_json():
    try:
        raw = sys.stdin.read()
    except Exception:
        return {}
    try:
        return json.loads(raw) if raw.strip() else {}
    except Exception:
        return {}


def resolve_cwd(payload):
    for key in ("cwd", "project_dir", "projectDir"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return os.getcwd()


def is_oracle(cwd):
    return os.path.basename(os.path.normpath(cwd or "")).endswith(ORACLE_SUFFIX)


def verdict(command):
    """None = allow. str = the reason this command cannot work, plus what to do instead."""
    m = SHOT_TMP.search(command)
    if m:
        return (
            "chromium บนเครื่องนี้เป็น snap ซึ่งมี /tmp ส่วนตัวของตัวเอง ⇒ `--screenshot=%s` "
            "จะไม่เขียนไฟล์อะไรเลย (ได้แค่ `Failed to write file … (2)` แล้วเดินต่อเหมือนสำเร็จ) · "
            "เขียนลงในโปรเจกต์แทน (โฟลเดอร์ซ่อนที่ซ้อนอยู่ข้างในเช่น `<proj>/.orches-shots/` ใช้ได้ "
            "แต่ `~/.something` ชั้นบนสุดโดน Permission denied) · ทางที่ดีกว่า: เรียก verb "
            "`render-check` ของ engine ซึ่งจัดการเรื่องนี้ให้แล้วและ assert ว่าไฟล์เกิดจริง"
        ) % m.group(1)
    m = PKILL_F.search(command)
    if m and "[" not in m.group(1):
        return (
            "`pkill -f %s` จะ match **เชลล์ที่รันคำสั่งนี้เอง** ด้วย (command line ของมันมีสตริงนั้นอยู่) "
            "⇒ ฆ่าคำสั่งตัวเอง (เคยได้ exit 144 จริง) แล้วเซิร์ฟเวอร์อาจยังรอด · แก้: ใส่วงเล็บให้ pattern "
            "match ตัวเองไม่ได้ เช่น `[n]ode src/index.js` · ถ้าเป็น preview ที่เปิดด้วย "
            "`.orches-preview.sh` ให้รันสคริปต์นั้นซ้ำ มันปิดให้ทั้ง process group"
        ) % m.group(1)
    return None


def main():
    payload = _stdin_json()
    if not is_oracle(resolve_cwd(payload)):
        return 0
    cmd = ((payload.get("tool_input") or {}).get("command") or "")
    if not isinstance(cmd, str) or not cmd:
        return 0
    why = verdict(cmd)
    if not why:
        return 0
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": why,
        }
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)   # fail open — never block work because the guard itself broke
