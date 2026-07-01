use crate::BoneRaw;
use std::collections::{HashMap, HashSet};

const STRICT_CONNECT_RATIO: f32 = 0.05;
const MIN_CONNECT_DIST: f32 = 0.0005;

// ฟังก์ชันภายใน: ใช้สำหรับประกอบร่าง Parent-Child Chain บนหน่วยความจำ
fn build_chains_internally(
    bone_inputs: &Vec<BoneRaw>,
) -> (
    HashMap<String, Option<String>>,
    HashMap<String, Vec<String>>,
) {
    let mut parent_map: HashMap<String, Option<String>> = HashMap::new();
    let mut children_map: HashMap<String, Vec<String>> = HashMap::new();

    // คำนวณ Euclidean Distance ระหว่างพิกัด 3D
    let dist = |p1: &[f32; 3], p2: &[f32; 3]| -> f32 {
        ((p1[0] - p2[0]).powi(2) + (p1[1] - p2[1]).powi(2) + (p1[2] - p2[2]).powi(2)).sqrt()
    };

    for child in bone_inputs {
        let child_head = child.head;
        let child_len = dist(&child.head, &child.tail);
        let threshold = (child_len * STRICT_CONNECT_RATIO).max(MIN_CONNECT_DIST);

        let mut best_dist = f32::INFINITY;
        let mut best_parent: Option<String> = None;

        for cand in bone_inputs {
            if cand.name == child.name {
                continue;
            }
            let d = dist(&child_head, &cand.tail);
            if d <= threshold && d < best_dist {
                best_dist = d;
                best_parent = Some(cand.name.clone());
            }
        }

        // ดักบั๊กกระดูกชี้เข้าตัวเอง (Self-Parenting Guard)
        if let Some(ref p) = best_parent {
            if p == &child.name {
                best_parent = None;
            }
        }

        parent_map.insert(child.name.clone(), best_parent.clone());
        if let Some(p) = best_parent {
            children_map
                .entry(p)
                .or_insert_with(Vec::new)
                .push(child.name.clone());
        }
    }

    // จัดลำดับตัวอักษรของกิ่งลูกเพื่อความเสถียรสูงสุดตอนแสดงผล
    for (_, children) in children_map.iter_mut() {
        children.sort();
    }

    (parent_map, children_map)
}

/// คำนวณหาระดับความลึกของกิ่งกระดูก {bone_name: depth} การันตีไม่ค้างด้วย Cycle Guard
pub fn compute_bone_depths(bone_inputs: &Vec<BoneRaw>) -> HashMap<String, usize> {
    let (parent_map, _) = build_chains_internally(bone_inputs);
    let mut depths = HashMap::new();

    for bone in bone_inputs {
        let mut depth = 0;
        let mut curr = parent_map.get(&bone.name).cloned().flatten();
        let mut visited_chain = HashSet::new();
        visited_chain.insert(bone.name.clone());

        while let Some(parent_name) = curr {
            // 🔥 CYCLE GUARD: เจอความสัมพันธ์แบบงูกินหาง สั่งทำลายลูปทันที
            if visited_chain.contains(&parent_name) {
                break;
            }
            visited_chain.insert(parent_name.clone());
            depth += 1;
            curr = parent_map.get(&parent_name).cloned().flatten();
        }
        depths.insert(bone.name.clone(), depth);
    }

    depths
}

/// จัดลำดับจัดเรียงรายชื่อบนหน้าจอ UI List โดยประมวลผลผ่าน Iterative DFS (ปลอด Recursion)
pub fn compute_bone_order(bone_inputs: &Vec<BoneRaw>) -> Vec<String> {
    let (parent_map, children_map) = build_chains_internally(bone_inputs);
    let mut roots: Vec<String> = bone_inputs
        .iter()
        .filter(|b| parent_map.get(&b.name).cloned().flatten().is_none())
        .map(|b| b.name.clone())
        .collect();

    roots.sort();

    let mut result = Vec::new();
    let mut visited = HashSet::new();

    // 🧠 ITERATIVE DFS STACK: ใช้ Stack จำลองการทำงาน ตัดโอกาสเกิด Stack Overflow ของระบบ
    for root in roots {
        let mut stack = vec![root];
        while let Some(curr) = stack.pop() {
            if visited.contains(&curr) {
                continue;
            }
            visited.insert(curr.clone());
            result.push(curr.clone());

            if let Some(children) = children_map.get(&curr) {
                for child in children.iter().rev() {
                    if !visited.contains(child) {
                        stack.push(child.clone());
                    }
                }
            }
        }
    }

    // เก็บตกกระดูกกลุ่มพิเศษที่วนลูปอยู่กลางอากาศ ให้ต่อแถวท้ายลิสต์แบบเรียงตัวอักษรปกติ
    let mut leftovers: Vec<String> = bone_inputs
        .iter()
        .map(|b| b.name.clone())
        .filter(|name| !visited.contains(name))
        .collect();
    leftovers.sort();
    result.extend(leftovers);

    result
}
