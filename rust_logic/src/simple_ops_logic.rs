use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};

use crate::norm;

// ═════════════════════════════════════════════════════════════════════════
//  Simple weight operations (Add / Scale / Sharpen) — Int-ID pipeline
// ═════════════════════════════════════════════════════════════════════════

// ── 🧠 Add ────────────────────────────────────────────────────────────

/// Add *intensity* to the active weight (or mask value).
/// Mirror of Python `add_logic.apply()` — ⚡ Int-ID pipeline.
#[pyfunction]
pub fn rust_add_logic(
    mut layer_dict: HashMap<i64, HashMap<i32, f64>>,
    mut mask_dict: HashMap<i64, f64>,
    selected_verts: Vec<i64>,
    active_vg_id: i32,
    intensity: f64,
    locks: HashMap<i32, bool>,
    #[allow(unused_variables)] active_layer_idx: i64,
    is_mask_mode: bool,
) -> PyResult<(HashMap<i64, HashMap<i32, f64>>, HashMap<i64, f64>)> {
    if is_mask_mode {
        for &v_idx in &selected_verts {
            let current = mask_dict.get(&v_idx).copied().unwrap_or(0.0);
            let new_w = (current + intensity).clamp(0.0, 1.0);
            mask_dict.insert(v_idx, new_w);
        }
        return Ok((layer_dict, mask_dict));
    }

    // ── Layer-weight mode (Int-ID keys, no string allocation) ────────
    for &v_idx in &selected_verts {
        let v_weights = layer_dict.entry(v_idx).or_default();
        let current = v_weights.get(&active_vg_id).copied().unwrap_or(0.0);
        v_weights.insert(active_vg_id, (current + intensity).clamp(0.0, 1.0));

        // Canonical in-place normalisation (no ownership-transfer overhead)
        norm::normalize_around_active_inplace(v_weights, active_vg_id, &locks);
    }

    Ok((layer_dict, mask_dict))
}

// ── 🧠 Scale ──────────────────────────────────────────────────────────

/// Multiply the active weight by *intensity*.
/// Mirror of Python `scale_logic.apply()` — ⚡ Int-ID pipeline.
#[pyfunction]
pub fn rust_scale_logic(
    mut layer_dict: HashMap<i64, HashMap<i32, f64>>,
    mut mask_dict: HashMap<i64, f64>,
    selected_verts: Vec<i64>,
    active_vg_id: i32,
    intensity: f64,
    locks: HashMap<i32, bool>,
    is_mask_mode: bool,
) -> PyResult<(HashMap<i64, HashMap<i32, f64>>, HashMap<i64, f64>)> {
    if is_mask_mode {
        for &v_idx in &selected_verts {
            let current = mask_dict.get(&v_idx).copied().unwrap_or(0.0);
            let new_w = (current * intensity).clamp(0.0, 1.0);
            mask_dict.insert(v_idx, new_w);
        }
        return Ok((layer_dict, mask_dict));
    }

    // ── Layer-weight mode (Int-ID keys, no string allocation) ────────
    let locked_bone_ids: HashSet<i32> = locks
        .iter()
        .filter(|&(&b_id, &locked)| locked && b_id != active_vg_id)
        .map(|(&b_id, _)| b_id)
        .collect();

    let unlocked_bone_ids: HashSet<i32> = locks
        .iter()
        .filter(|&(&b_id, &locked)| !locked && b_id != active_vg_id)
        .map(|(&b_id, _)| b_id)
        .collect();

    for &v_idx in &selected_verts {
        let vw_layer = layer_dict.entry(v_idx).or_default();

        let current_active = vw_layer.get(&active_vg_id).copied().unwrap_or(0.0);

        let other_total: f64 = unlocked_bone_ids
            .iter()
            .map(|b_id| vw_layer.get(b_id).copied().unwrap_or(0.0))
            .sum();

        if current_active < 0.0001 && other_total < 0.0001 {
            continue;
        }

        let mut new_active = current_active * intensity;

        let lock_total: f64 = locked_bone_ids
            .iter()
            .map(|b_id| vw_layer.get(b_id).copied().unwrap_or(0.0))
            .sum();
        let lock_total = lock_total.min(1.0);
        let max_allowed = (1.0 - lock_total).max(0.0);
        new_active = new_active.min(max_allowed);
        let remaining = (max_allowed - new_active).max(0.0);

        vw_layer.insert(active_vg_id, new_active);

        if remaining <= 0.00001 {
            for b_id in &unlocked_bone_ids {
                vw_layer.insert(*b_id, 0.0);
            }
            continue;
        }

        if other_total > 0.00001 {
            for b_id in &unlocked_bone_ids {
                let w = vw_layer.get(b_id).copied().unwrap_or(0.0);
                vw_layer.insert(*b_id, (w / other_total) * remaining);
            }
        } else if !unlocked_bone_ids.is_empty() {
            let equal_w = remaining / unlocked_bone_ids.len() as f64;
            for b_id in &unlocked_bone_ids {
                vw_layer.insert(*b_id, equal_w);
            }
        }
    }

    Ok((layer_dict, mask_dict))
}

// ── 🧠 Sharpen ────────────────────────────────────────────────────────

/// Formula: new = current + (current - avg) * intensity
/// Mirror of Python `sharpen_logic.apply()` — ⚡ Int-ID pipeline.
#[pyfunction]
pub fn rust_sharpen_logic(
    mut layer_dict: HashMap<i64, HashMap<i32, f64>>,
    mut mask_dict: HashMap<i64, f64>,
    selected_verts: Vec<i64>,
    neighbors: HashMap<i64, Vec<i64>>,
    active_vg_id: i32,
    intensity: f64,
    is_mask_mode: bool,
) -> PyResult<(HashMap<i64, HashMap<i32, f64>>, HashMap<i64, f64>)> {
    if is_mask_mode {
        let mut new_weights: HashMap<i64, f64> = HashMap::new();

        for &v_idx in &selected_verts {
            let current = mask_dict.get(&v_idx).copied().unwrap_or(0.0);

            let n_indices = neighbors.get(&v_idx);
            let n_weights: Vec<f64> = match n_indices {
                Some(ns) => ns
                    .iter()
                    .map(|n| mask_dict.get(n).copied().unwrap_or(0.0))
                    .collect(),
                None => vec![],
            };

            if !n_weights.is_empty() {
                let avg = n_weights.iter().sum::<f64>() / n_weights.len() as f64;
                let new_w = current + (current - avg) * intensity;
                new_weights.insert(v_idx, new_w.clamp(0.0, 1.0));
            } else {
                new_weights.insert(v_idx, current);
            }
        }

        for (v_idx, w) in new_weights {
            mask_dict.insert(v_idx, w);
        }
        return Ok((layer_dict, mask_dict));
    }

    // ── Layer-weight mode (Int-ID keys, no string allocation) ────────
    let mut new_weights: HashMap<i64, f64> = HashMap::new();

    for &v_idx in &selected_verts {
        let current = layer_dict
            .get(&v_idx)
            .and_then(|vw| vw.get(&active_vg_id))
            .copied()
            .unwrap_or(0.0);

        let n_indices = neighbors.get(&v_idx);
        let n_weights: Vec<f64> = match n_indices {
            Some(ns) => ns
                .iter()
                .map(|n| {
                    layer_dict
                        .get(n)
                        .and_then(|vw| vw.get(&active_vg_id))
                        .copied()
                        .unwrap_or(0.0)
                })
                .collect(),
            None => vec![],
        };

        if !n_weights.is_empty() {
            let avg = n_weights.iter().sum::<f64>() / n_weights.len() as f64;
            let new_w = current + (current - avg) * intensity;
            new_weights.insert(v_idx, new_w.clamp(0.0, 1.0));
        } else {
            new_weights.insert(v_idx, current);
        }
    }

    for (v_idx, w) in new_weights {
        layer_dict.entry(v_idx).or_default().insert(active_vg_id, w);
    }

    Ok((layer_dict, mask_dict))
}
