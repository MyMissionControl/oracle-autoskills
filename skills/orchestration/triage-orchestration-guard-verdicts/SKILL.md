---
name: triage-orchestration-guard-verdicts
description: 'Use when an orchestrator guard returns ALIVE/TIMEOUT/STALE that would stop the run, fork a second driver, or escalate a healthy worker — prove it from process, timestamps and disk before obeying'
installer: auto-skill
created_at: 2026-09-05T18:59:14+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'jack'
category: 'orchestration'
content_hash: 3b6819af8010f19dfe04d728cd2f3015162b5d8f4f774a8ae3d04dbc434597f8
---
# Triage an orchestration guard's scary verdict before obeying it

ใช้เมื่อ guard/verb ของ orchestrator คืน token ที่จะ **หยุดรัน / แตกตัวที่สอง / escalate** —
`ALIVE` (มี driver อื่นอยู่), `TIMEOUT`/`STALE` (worker แขวน), `PANE_GONE`, `IDLE` —
แล้วคุณกำลังจะเชื่อมันทั้งที่ยังไม่มีหลักฐานตรง

กฎเดียวของ skill นี้: **verdict คือสมมติฐาน ไม่ใช่ข้อเท็จจริง** ตรวจ 3 ชั้น (process → เวลา → ดิสก์)
ก่อนตัดสิน ทุกชั้นถูกเสมอต่อให้ verdict ผิด

## ทำไมถึงพลาดบ่อย
guard พวกนี้เขียนด้วย heuristic ที่ **ลำดับการเช็คมีผล**: เงื่อนไขที่เจอก่อนจะ `return` ทันที
ทำให้เงื่อนไขที่ควรยกเว้น (เช่น "เป็นตัวเราเอง") เข้าไม่ถึงเลย
อ่านฟังก์ชันจริงก่อน — 3 นาทีที่อ่านโค้ด guard ประหยัดการตัดสินใจผิดทั้งรอบ

```bash
SRC="$(readlink -f <path/ของ/engine.sh>)"
awk '/^cmd_<verb>\(\)/,/^}/' "$SRC"     # อ่านลำดับ return ของจริง
```

## ชั้น 1 — process: มีตัวจริงอีกตัวไหม
```bash
tmux list-panes -a -F '#{session_name}:#{window_index} id=#{pane_id} pid=#{pane_pid} cmd=#{pane_current_command}'
for p in $(tmux list-panes -a -F '#{pane_pid}'); do ps --ppid "$p" -o pid,etimes,args --no-headers; done
```
เจอ agent ตัวเดียว = ตัวเราเอง ⇒ verdict "มีคนอื่น" เป็น false positive

## ชั้น 2 — เวลา: ใครเป็นคนเขียน state ที่ guard อ่าน
```bash
ps -o pid,ppid,lstart,args --no-headers -p <my_pid>          # session/process เราเกิดตอนไหน
stat -c '%n mtime=%y' <proj>/<statefile>                      # state ถูกแตะตอนไหน
find <proj> -mmin -5 -not -path '*/node_modules/*' -printf '%TH:%TM:%TS %p\n' | sort
```
⛔ กับดักคลาสสิก: **launcher ของเราเองรีเฟรช heartbeat ตอนบูต** ⇒ guard เห็น "heartbeat สด"
แล้วสรุปว่ามี owner อื่นยัง live · ถ้า mtime ของ state == เวลาที่ process เราเกิด (ห่างไม่กี่ ms) = เราเขียนเอง

## ชั้น 3 — ดิสก์/หน้าจอ: worker "แขวน" จริงหรือแค่ไม่ commit
```bash
tmux capture-pane -t <pane> -p | tail -18          # หา spinner จริง
tmux capture-pane -t <pane> -p | grep -oE '([A-Za-z]+…) \([0-9]+m? ?[0-9]*s[^)]*'
git -C <worktree> log --oneline <base>..HEAD ; git -C <worktree> status --porcelain | wc -l
```
⛔ ตัวนับ timeout ของ engine มักนับจาก **"ครั้งสุดท้ายที่มี commit"** ไม่ใช่จากเวลาที่เริ่มรอ ⇒
agent ที่คิดยาว (reasoning effort สูง) หรือกำลัง **auto-compact** จะไม่มี commit ใหม่หลายสิบนาที = ดู "ไม่คืบหน้า"
เห็น `Compacting…` / spinner เดินอยู่ / มีไฟล์ใหม่บนดิสก์ = **ยังมีชีวิต ห้าม escalate**
แก้: ล้างตัวนับสะสมแล้วรอต่อ — `<engine> state-set <proj> pollstart-<role> ""` แล้วเรียก poll ใหม่
(ถ้าค่าสะสมใกล้เพดาน รอบถัดไปจะเด้ง TIMEOUT ทันทีทั้งที่เพิ่งเริ่มรอ)

## ตัดสิน
| หลักฐาน | ทำ |
|---|---|
| ชั้น 1 เจอ agent ตัวเดียว + ชั้น 2 ชี้ว่าเราเขียน state เอง | ถือว่า SELF เดินต่อได้ · **บอก user ว่า override เพราะอะไร** |
| ชั้น 3 เห็น spinner/ไฟล์ใหม่/commit เพิ่ม | ล้างตัวนับ แล้วรอต่อ ห้าม escalate |
| ชั้น 3 เงียบสนิท ไม่มีอะไรขยับข้ามหลายรอบ | เชื่อ verdict → escalate/รีเซ็ตตามคู่มือ |

⛔ ห้าม override เงียบ ๆ — เขียนหลักฐานที่ใช้ตัดสินให้ user เห็นเสมอ (ตาราง 3 บรรทัดก็พอ)
⛔ ถ้าหลักฐานขัดกันเอง ให้เชื่อ verdict (fail-closed) แล้วถาม user
