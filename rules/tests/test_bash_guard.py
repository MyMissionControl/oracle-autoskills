#!/usr/bin/env python3
"""Tests for the PreToolUse(Bash) guard. Stdlib only.  Run:  python3 test_bash_guard.py

The two shapes it blocks were both hit for real in one sprint, and both look like success from the
outside — that is the whole reason a rule in the prompt was not enough. What matters most here is
the NEGATIVE side: a guard that blocks ordinary work would be worse than the bug, so most of these
cases assert that normal commands sail through untouched.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(os.path.dirname(HERE), "bash_guard.py")
ORACLE = "/home/x/Desktop/soulbrew/github.com/fufu-2345/jack-oracle"
HUMAN = "/home/x/Desktop/soulbrew"

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
    else:
        FAIL += 1
        print("  FAIL %s %s" % (name, detail))


def run(cmd, cwd=ORACLE):
    p = subprocess.run([sys.executable, GUARD], input=json.dumps({
        "cwd": cwd, "tool_name": "Bash", "tool_input": {"command": cmd},
    }), capture_output=True, text=True)
    return p.stdout.strip(), p.returncode


def denied(cmd, cwd=ORACLE):
    out, rc = run(cmd, cwd)
    if not out:
        return None
    try:
        return json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"]
    except Exception:
        return None


def main():
    print("── บล็อกจริงสองรูปที่เคยพังเงียบ ──")
    r = denied('chromium --headless --screenshot="/tmp/claude-1000/x/shots/a.png" http://localhost:5183/')
    check("S1 --screenshot ลง /tmp = deny", r is not None)
    check("S2 ...บอกเหตุว่าเป็น snap", r and "snap" in r, r or "")
    check("S3 ...บอกทางที่ใช้ได้จริง", r and "render-check" in r, r or "")
    check("S4 path ที่ผิดถูกอ้างกลับมาให้เห็น", r and "/tmp/claude-1000/x/shots/a.png" in r, r or "")
    r = denied('pkill -f "node src/index.js"')
    check("P1 pkill -f = deny", r is not None)
    check("P2 ...บอกทางแก้ที่ทำได้ทันที", r and "[n]ode" in r, r or "")
    check("P3 pkill -9 -f ก็ต้องโดน", denied('pkill -9 -f vite') is not None)
    check("P4 pkill --full ไม่มี pattern ปลอดภัย ก็ยังโดน", denied("pkill -f 'concurrently -n a,b'") is not None)

    print("── ห้ามบล็อกงานปกติ (ด่านที่บล็อกผิด แย่กว่าบั๊กที่มันกัน) ──")
    check("N1 เขียนรูปในโปรเจกต์ = ผ่าน",
          denied('chromium --headless --screenshot="/home/x/p/.orches-shots/a.png" http://x/') is None)
    check("N2 --dump-dom เฉย ๆ = ผ่าน", denied("chromium --headless --dump-dom http://localhost:3000/") is None)
    # ⛔ วงเล็บ = pattern ที่ match ตัวเองไม่ได้ ⇒ เป็นทางแก้ที่เราแนะนำเอง ต้องผ่าน
    check("N3 pkill ที่ใส่วงเล็บแล้ว = ผ่าน", denied('pkill -f "[n]ode src/index.js"') is None)
    check("N4 pkill ธรรมดา (ไม่มี -f) = ผ่าน", denied("pkill vite") is None)
    check("N5 pgrep -f = ผ่าน (อ่านอย่างเดียว ไม่ฆ่าใคร)", denied('pgrep -af "node src"') is None)
    check("N6 คำสั่งทั่วไป = ผ่าน", denied("npm run build && git status") is None)
    check("N7 ไฟล์ /tmp ที่ไม่ใช่ screenshot = ผ่าน", denied("cat /tmp/x.log | tail -5") is None)

    print("── ขอบเขต: เฉพาะ session ของ oracle ──")
    check("B1 session ของคนใช้งาน ไม่โดนแตะ",
          denied('pkill -f "node src/index.js"', cwd=HUMAN) is None)
    check("B2 ...รวมถึงเคส screenshot ด้วย",
          denied('chromium --screenshot=/tmp/a.png http://x/', cwd=HUMAN) is None)
    out, rc = run("echo hi")
    check("B3 คำสั่งที่ผ่าน = ไม่พิมพ์อะไรเลย", out == "", out)
    check("B4 rc 0 เสมอ", rc == 0)

    print("── fail open ──")
    p = subprocess.run([sys.executable, GUARD], input="not json at all", capture_output=True, text=True)
    check("F1 stdin เจ๊ง = ไม่บล็อก + rc 0", p.returncode == 0 and p.stdout.strip() == "")
    p = subprocess.run([sys.executable, GUARD], input="", capture_output=True, text=True)
    check("F2 stdin ว่าง = ไม่บล็อก + rc 0", p.returncode == 0 and p.stdout.strip() == "")

    print("bash_guard: %d passed, %d failed" % (PASS, FAIL))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
