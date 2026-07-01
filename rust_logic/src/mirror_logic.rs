use pyo3::prelude::*;
use std::collections::{HashMap, HashSet};

use crate::norm;

// ── 🧠 Pure mirror-weight logic ─────────────────────────────────────────
// KDTree: brute-force O(V²) find-nearest (stand-in for mathutils.kdtree)
//
// ⚡ LOCAL ID MAPPING:
// - `rust_mirror_generate_pairs` stays string-based (pattern matching on names)
// - `rust_mirror_apply` uses Int-ID keys for layer_dict and id_pairs
// - `rust_mirror_apply_mask` has no bone dimension

// ── 🔧 Geometry Helpers ────────────────────────────────────────────────

#[inline]
fn is_source_side(coord: (f64, f64, f64), axis_idx: usize, direction: &str) -> bool {
    let eps = 1e-5_f64;
    let val = match axis_idx {
        0 => coord.0,
        1 => coord.1,
        _ => coord.2,
    };
    if direction == "POS_NEG" {
        val >= -eps
    } else {
        val <= eps
    }
}

#[inline]
fn is_target_side(coord: (f64, f64, f64), axis_idx: usize, direction: &str) -> bool {
    let eps = 1e-5_f64;
    let val = match axis_idx {
        0 => coord.0,
        1 => coord.1,
        _ => coord.2,
    };
    if direction == "POS_NEG" {
        val < -eps
    } else {
        val > eps
    }
}

fn flip_coord(coord: (f64, f64, f64), axis_idx: usize) -> (f64, f64, f64) {
    match axis_idx {
        0 => (-coord.0, coord.1, coord.2),
        1 => (coord.0, -coord.1, coord.2),
        _ => (coord.0, coord.1, -coord.2),
    }
}

fn vec3_dist_sq(a: (f64, f64, f64), b: (f64, f64, f64)) -> f64 {
    let dx = a.0 - b.0;
    let dy = a.1 - b.1;
    let dz = a.2 - b.2;
    dx * dx + dy * dy + dz * dz
}

/// Brute-force nearest-neighbour search (stand-in for mathutils.kdtree)
fn find_nearest(target: (f64, f64, f64), coords: &[(f64, f64, f64)]) -> (usize, f64) {
    let mut best_idx = 0_usize;
    let mut best_dist_sq = f64::MAX;

    for (i, &coord) in coords.iter().enumerate() {
        let d_sq = vec3_dist_sq(target, coord);
        if d_sq < best_dist_sq {
            best_dist_sq = d_sq;
            best_idx = i;
        }
    }

    (best_idx, best_dist_sq.sqrt())
}

// ── 🔧 Simple glob matching (stand-in for Python `re` module) ───────────

/// Match glob pattern (single `*` wildcard) against text.
/// Returns captured groups (text matching each `*`).
fn glob_capture(pattern: &str, text: &str) -> Option<Vec<String>> {
    if !pattern.contains('*') {
        return if pattern == text { Some(vec![]) } else { None };
    }

    let parts: Vec<&str> = pattern.split('*').collect();

    match parts.len() {
        2 => {
            let (pre, suf) = (parts[0], parts[1]);
            if pre.is_empty() && suf.is_empty() {
                return Some(vec![text.to_string()]);
            }
            if pre.is_empty() {
                // *suffix
                if text.ends_with(suf) && text.len() >= suf.len() {
                    Some(vec![text[..text.len() - suf.len()].to_string()])
                } else {
                    None
                }
            } else if suf.is_empty() {
                // prefix*
                if text.starts_with(pre) && text.len() >= pre.len() {
                    Some(vec![text[pre.len()..].to_string()])
                } else {
                    None
                }
            } else {
                // prefix*suffix
                if text.starts_with(pre)
                    && text.ends_with(suf)
                    && text.len() >= pre.len() + suf.len()
                {
                    Some(vec![text[pre.len()..text.len() - suf.len()].to_string()])
                } else {
                    None
                }
            }
        }
        3 => {
            let (p0, p1, p2) = (parts[0], parts[1], parts[2]);
            if p0.is_empty() && p2.is_empty() {
                // *mid*
                if let Some(pos) = text.find(p1) {
                    Some(vec![
                        text[..pos].to_string(),
                        text[pos + p1.len()..].to_string(),
                    ])
                } else {
                    None
                }
            } else {
                // ⚠️ 3+ wildcards (e.g. "L_*_arm_*_tip"): not implemented.
                // The Python `re`-based generate_pairs() this engine replaced
                // could handle arbitrary wildcard counts via regex and was
                // used as a fallback whenever this glob matcher's pair count
                // looked too low — that fallback no longer exists (see
                // core/rust_loader.py / CLAUDE.md Architecture intro), so a
                // search/replace rule with 2+ wildcards now silently fails
                // to pair those bones instead of degrading to regex matching.
                None
            }
        }
        _ => None,
    }
}

/// Apply glob substitution: replace `*` in replace_pattern with captured groups.
fn glob_replace(pattern: &str, text: &str, replace_pattern: &str) -> Option<String> {
    let groups = glob_capture(pattern, text)?;
    let mut result = String::new();
    let mut gi = 0_usize;
    for ch in replace_pattern.chars() {
        if ch == '*' {
            if gi < groups.len() {
                result.push_str(&groups[gi]);
                gi += 1;
            }
        } else {
            result.push(ch);
        }
    }
    Some(result)
}

// ══════════════════════════════════════════════════════════════════════
// 🚀 PUBLIC PYTHON PORTALS
// ══════════════════════════════════════════════════════════════════════

/// Mirror of Python `mirror_logic.generate_pairs()` — string-based
#[pyfunction]
pub fn rust_mirror_generate_pairs(
    vg_names: Vec<String>,
    bone_centers: HashMap<String, (f64, f64, f64)>,
    sr_list: Vec<(String, String)>,
    axis: String,
    direction: String,
) -> PyResult<HashMap<String, String>> {
    let axis_idx = match axis.as_str() {
        "X" => 0,
        "Y" => 1,
        "Z" => 2,
        _ => 0,
    };

    let vg_name_set: HashSet<&String> = vg_names.iter().collect();
    let mut pairs: HashMap<String, String> = HashMap::new();

    // Collect source-side bone names
    let mut source_vg_names: Vec<String> = Vec::new();
    for name in &vg_names {
        if let Some(&center) = bone_centers.get(name) {
            if is_source_side(center, axis_idx, &direction) {
                source_vg_names.push(name.clone());
            }
        }
    }

    for src_name in &source_vg_names {
        let mut matched = false;
        for (search_text, replace_text) in &sr_list {
            if search_text.is_empty() || replace_text.is_empty() {
                continue;
            }

            // Try both directions
            let search_pattern: Option<&str>;
            let replace_pattern: Option<&str>;

            if glob_capture(search_text, src_name).is_some() {
                search_pattern = Some(search_text.as_str());
                replace_pattern = Some(replace_text.as_str());
            } else if glob_capture(replace_text, src_name).is_some() {
                search_pattern = Some(replace_text.as_str());
                replace_pattern = Some(search_text.as_str());
            } else {
                continue;
            }

            let sp = search_pattern.unwrap();
            let rp = replace_pattern.unwrap();

            if let Some(target_name) = glob_replace(sp, src_name, rp) {
                if target_name != *src_name && vg_name_set.contains(&target_name) {
                    pairs.insert(src_name.clone(), target_name);
                    matched = true;
                    break;
                }
            }
        }

        if !matched {
            pairs.insert(src_name.clone(), src_name.clone());
        }
    }

    // Sort: unmatched (identity pairs) first
    let mut sorted_pairs: Vec<(String, String)> = pairs.into_iter().collect();
    sorted_pairs.sort_by_key(|(k, v)| if k == v { 0 } else { 1 });
    Ok(sorted_pairs.into_iter().collect())
}

/// Mirror of Python `mirror_logic.apply()` — ⚡ Int-ID pipeline
#[pyfunction]
pub fn rust_mirror_apply(
    mut layer_dict: HashMap<i64, HashMap<i32, f64>>,
    id_pairs: HashMap<i32, i32>,
    vertex_groups_lock: HashMap<i32, bool>,
    vertex_coords: Vec<(f64, f64, f64)>,
    axis: String,
    direction: String,
) -> PyResult<HashMap<i64, HashMap<i32, f64>>> {
    if id_pairs.is_empty() {
        return Ok(layer_dict);
    }

    let axis_idx = match axis.as_str() {
        "X" => 0,
        "Y" => 1,
        "Z" => 2,
        _ => 0,
    };

    let total_verts = vertex_coords.len();

    let pair_bone_ids: HashSet<i32> = id_pairs
        .iter()
        .flat_map(|(&src, &tgt)| vec![src, tgt])
        .collect();

    let mut modified_verts: HashSet<i64> = HashSet::new();

    // ══════════════════════════════════════════════════════════════
    // STEP 1 — SPLIT / SLICE
    // ══════════════════════════════════════════════════════════════
    for v_idx in 0..total_verts {
        let v_idx_i64 = v_idx as i64;
        let coord = vertex_coords[v_idx];

        if !is_target_side(coord, axis_idx, &direction) {
            continue;
        }

        let vw = match layer_dict.get(&v_idx_i64) {
            Some(vw) => vw,
            None => continue,
        };
        if vw.is_empty() {
            continue;
        }

        let cleaned: HashMap<i32, f64> = vw
            .iter()
            .filter(|&(&b_id, _)| !pair_bone_ids.contains(&b_id))
            .map(|(&b_id, &w)| (b_id, w))
            .collect();

        if cleaned.len() != vw.len() {
            if cleaned.is_empty() {
                layer_dict.remove(&v_idx_i64);
            } else {
                layer_dict.insert(v_idx_i64, cleaned);
            }
            modified_verts.insert(v_idx_i64);
        }
    }

    // ══════════════════════════════════════════════════════════════
    // STEP 2 — MIRROR (Brute-Force Nearest Neighbour)
    // ══════════════════════════════════════════════════════════════
    const KD_TREE_TOLERANCE: f64 = 0.05;

    // Collect vertices to process (layer_dict keys may change during iteration)
    let all_verts: Vec<i64> = layer_dict.keys().copied().collect();

    for (&src_id, &tgt_id) in &id_pairs {
        for &v_idx in &all_verts {
            let vw = match layer_dict.get(&v_idx) {
                Some(vw) => vw,
                None => continue,
            };

            if !vw.contains_key(&src_id) {
                continue;
            }

            let weight_val = *vw.get(&src_id).unwrap();
            if weight_val < 0.0001 {
                continue;
            }

            let coord = vertex_coords[v_idx as usize];

            if is_target_side(coord, axis_idx, &direction) {
                continue;
            }

            let flipped = flip_coord(coord, axis_idx);
            let (tgt_v_idx, dist) = find_nearest(flipped, &vertex_coords);
            let tgt_v_idx_i64 = tgt_v_idx as i64;

            if dist >= KD_TREE_TOLERANCE {
                continue;
            }

            layer_dict
                .entry(tgt_v_idx_i64)
                .or_default()
                .insert(tgt_id, weight_val);
            modified_verts.insert(tgt_v_idx_i64);
        }
    }

    // ══════════════════════════════════════════════════════════════
    // STEP 3 — NORMALIZE
    // ══════════════════════════════════════════════════════════════
    for v_idx in &modified_verts {
        if let Some(v_weights) = layer_dict.get_mut(v_idx) {
            norm::normalize_all_unlocked_inplace(v_weights, &vertex_groups_lock);
        }
    }

    Ok(layer_dict)
}

/// Mirror of Python `mirror_logic.apply_mask()`
#[pyfunction]
pub fn rust_mirror_apply_mask(
    mut mask_dict: HashMap<i64, f64>,
    vertex_coords: Vec<(f64, f64, f64)>,
    axis: String,
    direction: String,
) -> PyResult<HashMap<i64, f64>> {
    let axis_idx = match axis.as_str() {
        "X" => 0,
        "Y" => 1,
        "Z" => 2,
        _ => 0,
    };

    const KD_TREE_TOLERANCE: f64 = 0.05;

    for (v_idx_i64, coord) in vertex_coords.iter().enumerate() {
        let v_idx = v_idx_i64 as i64;

        if !is_source_side(*coord, axis_idx, &direction) {
            continue;
        }

        let val = mask_dict.get(&v_idx).copied().unwrap_or(1.0);
        let flipped = flip_coord(*coord, axis_idx);

        let (tgt_idx, dist) = find_nearest(flipped, &vertex_coords);
        let tgt_v_idx = tgt_idx as i64;

        if dist < KD_TREE_TOLERANCE {
            mask_dict.insert(tgt_v_idx, val);
        }
    }

    Ok(mask_dict)
}
