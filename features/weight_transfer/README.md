### 📦 5. `features/weight_transfer/README.md`

```markdown
# Weight Transfer Domain Specification

ระบบคัดลอกถอนรหัสค่าน้ำหนักผิวรูปทรงกระบอกทรงกลมจากโครงสร้างหุ่นจำลองต้นแบบ (Proxy Mesh) ไปยังชิ้นงานจริงผ่านหลักการเกลี่ยน้ำหนักเชิงเส้นอย่างแม่นยำ (Perfect Axial Linear Interpolation)

## ⚙️ Domain Actions Matrix

| Action | Operator ID | Purpose |
|---|---|---|
| `transfer_weight_maya` | `object.mw_copy_skin_weight_maya` | สั่งคำนวณและเกลี่ยพิกัดโอนถ่ายค่าน้ำหนักผิวสไตล์ซอฟต์แวร์ Maya |

## 🧬 Operational Mechanics (VG Context Bypass)
ฟีเจอร์นี้เป็นเครื่องมือชนิดพิเศษระดับตริตรองสูง (Toolkit) ซึ่งมีพฤติกรรมแตกต่างจากโดเมนอื่นในระบบ:
- **Direct Real-VG Mutation:** ตัวอัลกอริทึมจะทำงานหักล้างและเขียนข้อมูลลงไปบนโครงสร้าง **Live Vertex Groups ของ Blender โดยตรง** โดยจะทำการล้างกลุ่มเดิมบนวัตถุเป้าหมายและเขียนพิกัดน้ำหนักแกนหัวและท้ายแปรผันตามระยะห่างสมมาตรเวกเตอร์ `t = AP.dot(AB) / ab_length_sq`
- **Bypass Layer Storage:** ฟีเจอร์นี้จงใจข้ามขั้นตอนการทำงานผ่านโครงสร้างของ `LayerStorageService` เพื่อให้ผู้ใช้งานสามารถทำ Proxy Weight Transfer กับวัตถุดิบภายนอกได้อย่างรวดเร็ว

## 🚨 Rules for Agents
1. **Poll Context Guard:** ตัวคำสั่งจะทำงานได้ก็ต่อเมื่อผู้ใช้งานเลือกวัตถุประเภท MESH พร้อมกันอย่างน้อย 2 ชิ้นขึ้นไป (`len(context.selected_objects) >= 2`) โดยชิ้นที่เป็น Active Object จะถูกอนุมานเป็นตัวรับค่าน้ำหนักปลายทาง
2. **Armature Requirement:** วัตถุฝั่งต้นแบบ (Proxy Mesh) ต้องมีตัวดักจับและผูกโครงสร้างกระดูก Armature Modifier เอาไว้เสมอเพื่อใช้เป็นอินสแตนซ์อ้างอิงในการสร้างกลุ่มน้ำหนักให้กับผิววัตถุชิ้นใหม่