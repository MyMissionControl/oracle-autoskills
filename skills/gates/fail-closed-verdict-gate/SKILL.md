---
name: fail-closed-verdict-gate
description: Use when building a gate that reads an untrusted/LLM-authored verdict file (approve/reject) to decide merge/deploy. Parse first-line-only + bare-token + SHA-bind + asymmetric fail-closed.
installer: auto-skill
created_at: 2026-07-24T20:09:08+00:00
created_session: 
trigger: error-recovery
created_by: claude-opus-code
category: gates
content_hash: 9cff822b7e1d16307c80affe0809b019e56065c0aa5580cf0a00474746623d48
---
# Fail-closed parsing of an untrusted / LLM-authored verdict gate

เมื่อสร้าง "gate" ที่อ่านไฟล์คำตัดสิน (verdict/approval) ที่เขียนโดย agent/LLM หรือ source
ที่เชื่อไม่ได้เต็มร้อย แล้วใช้ตัดสิน merge/deploy/promote — ออกแบบให้ **fail-closed** ตาม 4 ข้อนี้
(แต่ละข้อคือกับดัก fail-OPEN ที่เจอจริง):

1. **อ่าน "บรรทัดแรกที่ไม่ว่าง" เท่านั้น — อย่า grep ทั้งไฟล์.**
   `grep -m1 '^APPROVE' file` สแกนทุกบรรทัด → ผู้เขียนขึ้นประโยคอธิบายด้วยคำ APPROVE แล้วปฏิเสธจริง
   บรรทัดล่าง = ถูกอ่านเป็นอนุมัติ (fail-OPEN). ใช้:
   `line="$(awk '{gsub(/\r/,"");sub(/^[[:space:]]+/,"");sub(/[[:space:]]+$/,"");if($0!=""){print;exit}}' file)"`
   (ตัด CR + whitespace หัวท้าย, exit บรรทัดแรกที่มีเนื้อ).

2. **โทเคน "อนุมัติ" ต้องมี word boundary — bare token เท่านั้น.** `case "$line" in APPROVE) ...` (เป๊ะ)
   ไม่ใช่ `APPROVE*` (จะจับ APPROVED/APPROVEXYZ/"APPROVE แต่จริงๆ ไม่..."). ถ้าอยากรับโน้ตต่อท้าย
   ให้บังคับตัวคั่นชัดเจน: `APPROVE|APPROVE[!A-Za-z0-9_]*` (ASCII bracket = locale-safe, ไม่พึ่ง UTF-8 glob).
   ทางที่ปลอดภัยสุด = บังคับให้เขียน bare token คำเดียว (โน้ตอยู่บรรทัดถัดไป) แล้วบอกใน prompt/brief ให้ชัด.

3. **ผูกคำอนุมัติกับ commit SHA (หรือ content hash) ที่ถูกตรวจ.** ถ้าไม่ผูก: อนุมัติ commit A ค้างไว้ →
   งานถูก push commit B (แก้ conflict/resume) → รอบถัดไปอ่านอนุมัติเก่า = merge B ที่ไม่เคยตรวจ.
   บันทึก `<gate>-sha=<sha>` ตอนสร้าง checkout/เริ่มตรวจ; ตอนจะใช้ ให้ยอมรับ APPROVE ก็ต่อเมื่อ
   `sha ที่บันทึก == rev-parse <tip ปัจจุบัน>` มิฉะนั้น downgrade เป็น PENDING (บังคับตรวจใหม่).
   เลียนแบบ pattern ของ test-cache ที่เก็บ `PASS@<sha>` แล้ว re-run เมื่อ tip เปลี่ยน.

4. **เอนไปทางปฏิเสธ/รอ (asymmetric).** APPROVE = เข้ม (ไม่ชัด → PENDING). REJECT = หลวม (ขึ้นต้นโทเคนก็พอ).
   ทุก path ที่ "ไม่แน่ใจ" (ไม่มีไฟล์ / parse ไม่ออก / SHA ไม่ตรง / gate hang) = ห้าม merge.
   และให้มี **cap** กับลูป reject/retry → emit สถานะ `*_CAPPED` เพื่อ escalate ถามคน อย่า park เงียบไม่รู้จบ.

**ทดสอบ (TDD, RED ก่อน):** เขียน case ยิงตรงกับดัก — preamble-approve-then-reject, prefix-trap (APPROVED),
question-form (APPROVE?), indented token, blank-then-token, stale-SHA (อนุมัติแล้ว tip เดินหน้า → PENDING),
reject-ซ้ำถึง cap → CAPPED. ทุกอันต้อง fail ก่อนแก้.

**ยืนยัน invariant สำคัญ:** ถ้า gate เป็น opt-in/default-OFF ให้ verify ว่าปิดอยู่ = พฤติกรรมเดิม byte-identical
(diff ต้อง pure-additive ในบล็อกที่ guard ด้วยเงื่อนไข "เปิด" · probe ทุกค่า OFF).
