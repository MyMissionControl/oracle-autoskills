---
name: verify-layout-change-against-consumers
description: 'Use when adding/moving/renaming files or folders that other tools read (doc browsers, indexers, vault builders). Prove each consumer sees it by running its real listing functions on a fixture.'
installer: auto-skill
created_at: 2026-08-06T10:17:16+07:00
created_session: 
trigger: 'reusable-workflow'
created_by: 'main-chat'
category: 'docs'
content_hash: 907e50fe1051adcf605fd2eee1d60ec23c11e38d0b404fbe3dc8807b3c6e8554
---
# Verify a docs/layout change against its real consumers

เมื่อจะเพิ่ม/ย้าย/เปลี่ยนชื่อไฟล์-โฟลเดอร์ในโครงเอกสารหรือ artifact ที่มี "ผู้บริโภค" หลายตัว
(UI ที่ลิสต์ไฟล์, indexer, vault/symlink builder, search) — **ห้ามสรุปจากการอ่านโค้ด** ว่าเห็นหรือไม่เห็น
อ่านโค้ดตอบได้แค่ "น่าจะ" · รันฟังก์ชันจริงตอบว่า "เห็น/ไม่เห็น"

## ขั้นตอน

1. **ลิสต์ผู้บริโภคก่อนออกแบบ ไม่ใช่หลังสร้างเสร็จ** — grep หาโค้ดที่ `readdir`/`glob`/`walk` โฟลเดอร์นั้น
   ```bash
   grep -rnE "readdir|glob|walk|listFiles" --include='*.ts' --include='*.py' <repo>/src | grep -i <โฟลเดอร์>
   ```
   ทำ **ก่อน** เพราะผลอาจเปลี่ยนดีไซน์ (ผู้บริโภคอ่านแบบแบน = โฟลเดอร์ซ้อนจะไม่โผล่)

2. **ดูสองอย่างต่อผู้บริโภคหนึ่งตัว**
   - เดินแบบ recursive ไหม (โฟลเดอร์ย่อยรอดไหม)
   - มี ignore-list / max-depth / ตัวกรองนามสกุลไหม — ชื่อใหม่ไปตรงกับ ignore-list พอดีหรือเปล่า

3. **เขียนสคริปต์ทิ้ง 1 ไฟล์ที่ import ฟังก์ชันจริง แล้วยิงใส่ fixture ชั่วคราว**
   - fixture = โครงใหม่ + ของเดิมปนกัน (พิสูจน์ว่าไม่ไปทับของเดิม)
   - print ผลลัพธ์ออกมาให้เห็นเป็นรายการ ไม่ใช่แค่ assert true/false
   - วางสคริปต์ใน scratchpad และ import ด้วย **absolute path** — อย่าไปวางไฟล์ในรีโปของคนอื่น
   ```ts
   const { listX } = await import(`${ABS_SRC}/module.ts`);
   const P = fs.mkdtempSync("/tmp/check-"); /* สร้างโครง */ console.log(listX(P));
   ```

4. **ยิงกับข้อมูลจริง 1 ชุดด้วย — แต่กับ "สำเนา" ไม่ใช่ของจริง**
   ```bash
   W=$(mktemp -d); cp -r <ของจริง>/<ส่วนที่ต้องใช้> $W/p/; <คำสั่ง> "$W/p"; rm -rf $W
   ```
   ขั้นนี้จับบั๊กที่ fixture สังเคราะห์จับไม่ได้ (ข้อมูลจริงมีขนาด/ชื่อ/อักขระที่ไม่ได้คิดถึง)

5. **รายงานสิ่งที่ผู้บริโภค "ยังไม่เห็น" ด้วย** — ถ้าเจอช่องโหว่ที่มีอยู่ก่อนแล้ว (ไม่ได้เกิดจากงานนี้)
   ให้บอกแยกให้ชัดว่าเป็นของเดิม ไม่ใช่ regression

## กับดักที่เจอบ่อย
- `printf '---|'` / format ที่ขึ้นต้นด้วย `-` → shell อ่านเป็น option แล้ว printf ตายเงียบ ใช้ `printf '%s' '---|'`
- `local A="$1" B="$A"` ใน bash → `$A` ถูกขยายก่อนกำหนดค่า = unbound ใต้ `set -u` (แยกเป็น 2 บรรทัด)
- เทสที่ grep หาแพตเทิร์นทั่วไป (`^|---|`) จะไปเจอตารางอื่นในไฟล์เดียวกันก่อน — จำกัดขอบเขตด้วย
  `sed -n '/marker-เปิด/,/marker-ปิด/p'` ก่อน grep
