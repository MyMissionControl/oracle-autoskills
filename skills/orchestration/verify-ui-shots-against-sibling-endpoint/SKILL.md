---
name: verify-ui-shots-against-sibling-endpoint
description: 'ตรวจหลักฐานภาพหน้าจอของ role UI ที่พึ่ง endpoint ของ role พี่น้องใน sprint เดียวกัน — กันด่านออกใบรับรองให้ error state ที่ทำมาสวย + วินิจฉัย process ค้างพอร์ตที่ทำให้แคปซ้ำได้ภาพเดิม'
installer: auto-skill
created_at: 2026-08-17T13:24:54+07:00
created_session: 
trigger: 'error-recovery'
created_by: 'foreman'
category: 'orchestration'
content_hash: 129da55198f6580cfb77be4cf5e0ea7685dce4c895579aa61c5825e73e464dc7
---
# ตรวจหลักฐานภาพหน้าจอของ role UI ที่กินข้อมูลจาก endpoint ของ role พี่น้องใน sprint เดียวกัน

## เมื่อไหร่ใช้
sprint ที่ทำขนาน 2 role แล้ว role ฝั่ง UI ต้องแสดงข้อมูลจาก endpoint/service ที่ role อีกตัว
กำลังสร้าง **ใน sprint เดียวกัน** (ยังไม่ merge เข้า worktree ของ UI) · ใช้ตอนกำลังเขียน brief
และตอนก่อน land — ไม่ใช่หลังเจอปัญหา

## ปัญหาที่กันได้ (เกิดจริง)
worktree ของ UI ยังไม่มี endpoint → หน้าที่ควรโชว์ฟีเจอร์หลักกลายเป็น error state → ด่านภาพหน้าจอ
(`render-check` / `shots-seen` หรือเทียบเท่า) **ผ่านหมด** เพราะมันตรวจว่า "มีรูปและมีคนเปิดดู"
ไม่ได้ตรวจว่า "รูปนั้นคือฟีเจอร์ที่ทำงาน" → merge สปรินต์สุดท้ายโดยไม่มีใครเคยเห็นฟีเจอร์หลักทำงานเลย

## ขั้นตอน

### 1. ตอนเขียน brief ของ role UI — ห้ามเชิญหลักฐานปลอม
⛔ ห้ามเขียนว่า "endpoint ยังไม่ merge ระหว่างนี้ให้ทำ error state ให้สวย"
✅ เขียนแทนว่า:
```
endpoint <NAME> ยังไม่ merge เข้า worktree นี้ · เขียนโค้ดตามสัญญาใน <design-doc> ไปเลย
⛔ ห้ามรัน render-check/แคปรูปหน้า <ROUTE> จนกว่า orchestrator จะ sync main ที่มี endpoint นั้นให้แล้ว
```

### 2. ตอน role UI แจ้งเสร็จ — sync ก่อน แล้วบังคับแคปรอบใหม่
```bash
<INTG> sync "<PROJ>" <ui-role>      # ดึง main ที่มี endpoint ของ role พี่น้องเข้า branch
```
แล้วส่งขั้นตอนนี้ให้ worker ทำ **เรียงตามลำดับ** (ลำดับสำคัญ — ห้ามให้ขั้นแคปเป็นขั้นแรกที่รู้ว่าพัง):
```
1) ss -ltnp | grep -E ':<PORT_A>|:<PORT_B>'   → มีอะไรค้างให้ปิดให้หมดก่อน
2) เตรียมข้อมูล/สตาร์ท service ของ worktree ตัวเอง
3) พิสูจน์ด้วย curl ว่า endpoint คืน 200 พร้อมข้อมูลจริง — ยังไม่ได้ 200 ห้ามแคป
4) แล้วค่อยรัน render-check (path เต็ม ห้ามย่อ)
5) เปิดดูรูป "ทุกใบที่เป็นหน้าต่างกัน" ด้วย Read tool ใหม่ทั้งหมด
6) อัปเดตไฟล์ notes ให้ตรงความจริงรอบนี้ แล้วแตะ marker เสร็จใหม่
```

### 3. orchestrator เปิดรูปดูเอง — ทุกครั้ง ไม่เชื่อรายงาน
```bash
# ยิง endpoint เองเทียบกับสิ่งที่เห็นในรูป (คนละแหล่งกัน = พิสูจน์ได้จริง)
curl -s -c /tmp/ck.txt -X POST localhost:<PORT_API>/<login-path> -H 'Content-Type: application/json' -d '<creds-json>'
curl -s -b /tmp/ck.txt localhost:<PORT_API>/<endpoint>
```
เลขในผลลัพธ์ต้องตรงกับเลขที่เห็นในรูป · ไม่ตรง = หลักฐานผิด ตีกลับ

## กับดักที่ทำให้แคปซ้ำแล้วได้ภาพเดิมเป๊ะ
- **process เก่าค้างพอร์ต**: dev-proxy ยิงไปโดน service เก่าที่ไม่มี route ใหม่ · worker แคปกี่รอบก็ได้ภาพเดิม
  → **สงสัยพอร์ตค้างก่อนสงสัยโค้ด** เมื่อภาพไม่เปลี่ยนเลยหลังแก้
- **ด่าน shots-seen นับ Read จาก transcript เทิร์นล่าสุด ไม่ได้นับสะสมข้ามรอบ** → ทุกครั้งที่แคปใหม่
  ต้องสั่งเปิดดูครบทุกใบใหม่ ไม่ใช่แค่ใบที่สงสัย (ไม่งั้นได้ PARTIAL n/m ทั้งที่รอบก่อนดูครบ)
- **route ที่ครอบด้วย guard component**: ถ้าด่านสแกน route ด้วย regex บรรทัดเดียว
  `<Route ... element={<Guard><X /></Guard>} />` ต้องเขียนบรรทัดเดียว จัด multi-line แล้วด่านมองไม่เห็น route เงียบ ๆ
- **ตัวตรวจ responsive ที่วัด bounding-rect รายตัว** จะฟ้อง OVERFLOW กับตารางที่จงใจใส่ `overflow-x-auto` เสมอ
  → เทียบกับ `document.scrollWidth` แล้วเปิดรูปดูเอง อย่าเชื่อและอย่าปัดทิ้งทั้งคู่

## เกณฑ์ผ่าน
รูปของหน้าที่เป็นฟีเจอร์หลัก **แสดงข้อมูลจริง** ที่ตัวเลขตรงกับที่ orchestrator ยิง endpoint ได้เอง
ทุกขนาดจอที่ประกาศไว้ · ไม่ใช่ error state ที่ทำมาสวย
