use pyo3::prelude::*;
use std::collections::HashMap;

// ── 🧠 Pure normalisation helpers (Int-ID Keys) ───────────────────────

/// In-place normalise: clamp the active bone weight so unlocked weights
/// sum to 1.0 - lock_total.  Operates on ``&mut HashMap<i32, f64>``
/// so the call site pays zero ownership-transfer cost.
pub(crate) fn normalize_around_active_inplace(
    v_weights: &mut HashMap<i32, f64>,
    active_vg_id: i32,
    locks: &HashMap<i32, bool>,
) {
    let mut lock_total = 0.0_f64;
    let mut unlocked_bone_ids: Vec<i32> = Vec::new();
    let mut other_total = 0.0_f64;

    let active_weight = v_weights.get(&active_vg_id).copied().unwrap_or(0.0);

    for (&b_id, &w) in v_weights.iter() {
        if b_id == active_vg_id {
            continue;
        }
        if *locks.get(&b_id).unwrap_or(&false) {
            lock_total += w;
        } else if w > 0.0 {
            unlocked_bone_ids.push(b_id);
            other_total += w;
        }
    }

    lock_total = lock_total.min(1.0);
    let max_allowed_active = (1.0 - lock_total).max(0.0);
    let active_weight = active_weight.min(max_allowed_active);

    v_weights.insert(active_vg_id, active_weight);
    let remaining = (1.0 - lock_total - active_weight).max(0.0);

    if unlocked_bone_ids.is_empty() {
        v_weights.insert(active_vg_id, max_allowed_active);
        return;
    }

    if remaining <= 0.00001 {
        for &b_id in &unlocked_bone_ids {
            v_weights.insert(b_id, 0.0);
        }
        return;
    }

    if other_total > 0.0 {
        let inv_other = 1.0 / other_total;
        for &b_id in &unlocked_bone_ids {
            let w = v_weights.get(&b_id).copied().unwrap_or(0.0);
            v_weights.insert(b_id, w * inv_other * remaining);
        }
    } else {
        let fallback = remaining / unlocked_bone_ids.len() as f64;
        for &b_id in &unlocked_bone_ids {
            v_weights.insert(b_id, fallback);
        }
    }
}

/// In-place normalise: scale every unlocked weight proportionally so
/// they sum to 1.0 - lock_total.  Zero ownership-transfer overhead.
pub(crate) fn normalize_all_unlocked_inplace(
    v_weights: &mut HashMap<i32, f64>,
    locks: &HashMap<i32, bool>,
) {
    let mut lock_total = 0.0_f64;
    let mut unlocked: Vec<(i32, f64)> = Vec::new();

    for (&b_id, &w) in v_weights.iter() {
        if *locks.get(&b_id).unwrap_or(&false) {
            lock_total += w;
        } else if w > 0.0 {
            unlocked.push((b_id, w));
        }
    }

    lock_total = lock_total.min(1.0);
    let remaining = (1.0 - lock_total).max(0.0);

    if unlocked.is_empty() {
        return;
    }

    let unlocked_total: f64 = unlocked.iter().map(|(_, w)| w).sum();
    if unlocked_total < 0.0001 {
        return;
    }

    let scale = remaining / unlocked_total;
    for (b_id, _) in &unlocked {
        if let Some(w) = v_weights.get_mut(b_id) {
            *w *= scale;
        }
    }

    // 🧹 Clean near-zero entries that aren't locked
    v_weights.retain(|b_id, w| *w >= 0.0001 || *locks.get(b_id).unwrap_or(&false));
}

// ── 🚀 PyO3 portals (thin wrappers that take ownership for FFI compat) ──

/// Mirror of Python `normalize_around_active` in `_norm.py` — ⚡ Int-ID pipeline.
#[pyfunction]
pub fn rust_normalize_around_active(
    mut v_weights: HashMap<i32, f64>,
    active_vg_id: i32,
    locks: HashMap<i32, bool>,
    #[allow(unused_variables)] active_layer_idx: i64,
) -> PyResult<HashMap<i32, f64>> {
    normalize_around_active_inplace(&mut v_weights, active_vg_id, &locks);
    Ok(v_weights)
}

/// Mirror of Python `normalize_all_unlocked` in `_norm.py` — ⚡ Int-ID pipeline.
#[pyfunction]
pub fn rust_normalize_all_unlocked(
    mut v_weights: HashMap<i32, f64>,
    locks: HashMap<i32, bool>,
) -> PyResult<HashMap<i32, f64>> {
    normalize_all_unlocked_inplace(&mut v_weights, &locks);
    Ok(v_weights)
}
