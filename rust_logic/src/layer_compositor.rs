use std::collections::HashMap;

/// Top-down alpha-blend compositor — the sole implementation of SuperSkinPro's
/// layer stack flattening (no Python fallback; see core/rust_loader.py).
///
/// `meta_list` arrives already reordered bottom-to-top by the Python caller
/// (`compositor.py::composite_layers`) — the first entry processed here is
/// the foundation (`is_base == true`) layer.
///
/// - **Base layer**: initializes `accumulated[v_idx]` directly, scaled by
///   that vertex's mask value. Any vertex the base layer has no data for is
///   explicitly cleared (not left over from a previous mesh state).
/// - **Overlay layers**: "over" alpha compositing per vertex — existing
///   `accumulated` weights are scaled down by `(1 - v_mask)` (the overlay's
///   mask determines how much of what's underneath shows through), then the
///   overlay's own weights (pre-normalized so they sum to 1 within the
///   layer) are added back in scaled by `v_mask`. A vertex the overlay has
///   no weight for, or whose mask is ~0, is left untouched — `continue`,
///   not a zero-write, so non-overlapping regions of separate layers don't
///   erase each other.
/// - **Final pass**: every vertex's accumulated bone weights are renormalized
///   to sum to 1.0 (compositing math can drift slightly off 1.0 across many
///   layers), and near-zero entries (<=0.001) are dropped.
pub fn composite_layers_engine(
    meta_list: Vec<HashMap<String, f32>>,
    // 🔧 เปลี่ยน inner key จาก i32 → String (bone name โดยตรง)
    layer_data_map: HashMap<usize, HashMap<usize, HashMap<String, f32>>>,
    mask_data_map: HashMap<usize, HashMap<usize, f32>>,
    // 🔧 ลบ idx_to_name ออก ไม่จำเป็นอีกต่อไป
    num_verts: usize,
) -> HashMap<usize, HashMap<String, f32>> {
    let mut accumulated: Vec<HashMap<String, f32>> = vec![HashMap::new(); num_verts];

    for layer_meta in &meta_list {
        let l_idx = *layer_meta.get("index").unwrap_or(&0.0) as usize;
        let mask_default = *layer_meta.get("mask_default").unwrap_or(&1.0);

        let layer_dict = match layer_data_map.get(&l_idx) {
            Some(d) => d,
            None => continue,
        };

        let mask_dict = mask_data_map.get(&l_idx);
        let is_base = layer_meta.get("is_base").map_or(false, |&v| v > 0.5);

        for v_idx in 0..num_verts {
            let mut v_mask = match mask_dict {
                Some(md) => *md.get(&v_idx).unwrap_or(&mask_default),
                None => mask_default,
            };
            v_mask = v_mask.clamp(0.0, 1.0);

            let vw = match layer_dict.get(&v_idx) {
                Some(w) => w,
                None => {
                    if is_base {
                        accumulated[v_idx].clear();
                    }
                    continue;
                }
            };

            if is_base {
                accumulated[v_idx].clear();
                for (bone_name, &w) in vw {
                    // 🔧 ใช้ bone_name String โดยตรง ไม่ต้อง lookup idx_to_name
                    accumulated[v_idx].insert(bone_name.clone(), w * v_mask);
                }
            } else {
                if vw.is_empty() || v_mask <= 0.0001 {
                    continue;
                }
                let above_total: f32 = vw.values().sum();
                if above_total <= 0.0001 {
                    continue;
                }

                for w_accum in accumulated[v_idx].values_mut() {
                    *w_accum *= 1.0 - v_mask;
                }

                let inv_above = 1.0 / above_total;
                for (bone_name, &w_raw) in vw {
                    // 🔧 ใช้ bone_name String โดยตรง
                    let w_norm = w_raw * inv_above;
                    let entry = accumulated[v_idx].entry(bone_name.clone()).or_insert(0.0);
                    *entry += w_norm * v_mask;
                }
            }
        }
    }

    let mut result: HashMap<usize, HashMap<String, f32>> = HashMap::new();
    for v_idx in 0..num_verts {
        let bone_weights = &accumulated[v_idx];
        let total: f32 = bone_weights.values().sum();
        if total > 0.001 {
            let inv = 1.0 / total;
            let normed: HashMap<String, f32> = bone_weights
                .iter()
                .filter_map(|(name, &w)| {
                    let fw = w * inv;
                    if fw > 0.001 {
                        Some((name.clone(), fw))
                    } else {
                        None
                    }
                })
                .collect();
            if !normed.is_empty() {
                result.insert(v_idx, normed);
            }
        }
    }
    result
}
