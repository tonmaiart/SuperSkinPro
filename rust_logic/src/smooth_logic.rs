use std::collections::{HashMap, HashSet};

use crate::norm;

/// Smooth weights across neighbouring vertices using Integer Bone IDs.
/// Public entry point called from lib.rs FFI bridge.
pub fn apply_smooth_engine(
    mut layer_dict: HashMap<usize, HashMap<i32, f64>>,
    mut mask_dict: HashMap<usize, f64>,
    selected_verts: Vec<usize>,
    neighbors_map: HashMap<usize, Vec<usize>>,
    intensity: f64,
    vertex_groups_lock: HashMap<i32, bool>,
    affected_only: bool,
    is_mask_mode: bool,
) -> (HashMap<usize, HashMap<i32, f64>>, HashMap<usize, f64>) {
    let selected_set: HashSet<usize> = selected_verts.iter().cloned().collect();

    if is_mask_mode {
        let mut new_masks = HashMap::new();
        for &v_idx in &selected_verts {
            let current = *mask_dict.get(&v_idx).unwrap_or(&0.0);
            if affected_only && current <= 0.0001 {
                new_masks.insert(v_idx, 0.0);
                continue;
            }

            let mut valid_n = neighbors_map.get(&v_idx).cloned().unwrap_or_else(Vec::new);
            if affected_only {
                valid_n.retain(|n| selected_set.contains(n));
            }

            if !valid_n.is_empty() {
                let sum_n: f64 = valid_n
                    .iter()
                    .map(|n| *mask_dict.get(n).unwrap_or(&0.0))
                    .sum();
                let avg = sum_n / (valid_n.len() as f64);
                let new_val = current + (avg - current) * intensity;
                new_masks.insert(v_idx, new_val.clamp(0.0, 1.0));
            } else {
                new_masks.insert(v_idx, current);
            }
        }

        for (v_idx, val) in new_masks {
            mask_dict.insert(v_idx, val);
        }
        return (layer_dict, mask_dict);
    }

    // ── Layer-weight mode (Int-ID Keys, no string allocation) ────────
    let unlocked_vg_ids: Vec<i32> = vertex_groups_lock
        .iter()
        .filter(|&(_, &locked)| !locked)
        .map(|(&id, _)| id)
        .collect();

    // Build weight cache: vg_id → v_idx → weight
    let mut weight_cache: HashMap<i32, HashMap<usize, f64>> = HashMap::new();
    for &vg_id in &unlocked_vg_ids {
        let mut gi_cache = HashMap::new();
        for &v_idx in &selected_verts {
            gi_cache.insert(
                v_idx,
                *layer_dict
                    .get(&v_idx)
                    .and_then(|vw| vw.get(&vg_id))
                    .unwrap_or(&0.0),
            );
            if let Some(ns) = neighbors_map.get(&v_idx) {
                for &n in ns {
                    gi_cache.entry(n).or_insert_with(|| {
                        *layer_dict
                            .get(&n)
                            .and_then(|vw| vw.get(&vg_id))
                            .unwrap_or(&0.0)
                    });
                }
            }
        }
        weight_cache.insert(vg_id, gi_cache);
    }

    for &v_idx in &selected_verts {
        let mut valid_n = neighbors_map.get(&v_idx).cloned().unwrap_or_else(Vec::new);
        if affected_only {
            valid_n.retain(|n| selected_set.contains(n));
        }

        let v_weights = layer_dict.entry(v_idx).or_insert_with(HashMap::new);

        for &vg_id in &unlocked_vg_ids {
            let gi_cache = weight_cache.get(&vg_id).unwrap();
            let current = *gi_cache.get(&v_idx).unwrap_or(&0.0);

            if affected_only && current <= 0.0001 {
                v_weights.insert(vg_id, 0.0);
                continue;
            }

            if !valid_n.is_empty() {
                let sum_n: f64 = valid_n
                    .iter()
                    .map(|n| *gi_cache.get(n).unwrap_or(&0.0))
                    .sum();
                let avg = sum_n / (valid_n.len() as f64);
                let new_w = current + (avg - current) * intensity;
                v_weights.insert(vg_id, new_w);
            } else {
                v_weights.insert(vg_id, current);
            }
        }

        // 🧹 Normalize per-vertex unlocked weights back to 1.0 - lock_total,
        // unconditionally — not just when blending happened. When
        // affected_only is on, near-zero bones are hard-set to 0.0 above
        // (skipping the blend formula entirely), which breaks the
        // sum-preserving property the blend formula otherwise guarantees.
        // This call is what absorbs that — removing it (or making it
        // conditional) leaves affected_only-smoothed vertices under 1.0.
        norm::normalize_all_unlocked_inplace(v_weights, &vertex_groups_lock);
    }

    (layer_dict, mask_dict)
}
