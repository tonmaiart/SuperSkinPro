use pyo3::prelude::*;
use std::collections::HashMap;

// ── 🧠 Pure auto-assign logic — BVH handled Python-side ───────────────
// Scoring math ported to Rust. Python pre-computes hit_count_map via BVH.

/// Score each bone against each vertex, return closest bone per vertex.
/// Mirror of Python `auto_logic.apply()` — BVH ray_cast replaced with pre-computed hit_count_map.
#[pyfunction]
pub fn rust_auto_logic(
    selected_verts: Vec<i64>,
    vertex_world_coords: Vec<(f64, f64, f64)>,
    bone_data: Vec<(String, (f64, f64, f64), (f64, f64, f64))>,
    bone_name_to_name: HashMap<String, String>,
    hit_count_map: HashMap<i64, HashMap<String, i64>>,
) -> PyResult<HashMap<i64, String>> {
    let mut result: HashMap<i64, String> = HashMap::new();

    for &v_idx in &selected_verts {
        let v_w = vertex_world_coords
            .get(v_idx as usize)
            .copied()
            .unwrap_or((0.0, 0.0, 0.0));

        let vertex_hits = hit_count_map.get(&v_idx);

        let mut best_bone_name: Option<String> = None;
        let mut min_score = f64::INFINITY;

        for (name, head, tail) in &bone_data {
            let head_v = *head;
            let tail_v = *tail;
            let bone_vec = vec3_sub(tail_v, head_v);
            let bone_len_sq = vec3_dot(bone_vec, bone_vec);

            let score = if bone_len_sq < 1e-12 {
                vec3_len(vec3_sub(v_w, head_v)) * 2.0
            } else {
                let bone_len = bone_len_sq.sqrt();
                let to_vert = vec3_sub(v_w, head_v);
                let percent = vec3_dot(to_vert, bone_vec) / bone_len_sq;
                let percent_clamped = percent.clamp(0.0, 1.0);
                let closest_pt = vec3_add(head_v, vec3_scale(bone_vec, percent_clamped));

                let radial_dist = vec3_len(vec3_sub(v_w, closest_pt));

                let axial_penalty = if percent < 0.0 {
                    (-percent) * bone_len
                } else if percent > 1.0 {
                    (percent - 1.0) * bone_len
                } else {
                    0.0
                };

                let mut score = radial_dist * 2.0 + axial_penalty * 0.5;

                // 🛡️ Occlusion penalty from pre-computed hit_count_map
                if radial_dist > 0.0001 {
                    if let Some(hits) = vertex_hits {
                        let hit_count = hits.get(name).copied().unwrap_or(0);
                        if hit_count > 1 {
                            score += 100.0 * hit_count as f64;
                        }
                    }
                }

                score
            };

            if score < min_score {
                min_score = score;
                best_bone_name = Some(name.clone());
            }
        }

        if let Some(best_name) = best_bone_name {
            if let Some(mapped_name) = bone_name_to_name.get(&best_name) {
                result.insert(v_idx, mapped_name.clone());
            }
        }
    }

    Ok(result)
}

// ── 🔧 Inline 3D vector helpers ──────────────────────────────────────

#[inline]
fn vec3_sub(a: (f64, f64, f64), b: (f64, f64, f64)) -> (f64, f64, f64) {
    (a.0 - b.0, a.1 - b.1, a.2 - b.2)
}

#[inline]
fn vec3_add(a: (f64, f64, f64), b: (f64, f64, f64)) -> (f64, f64, f64) {
    (a.0 + b.0, a.1 + b.1, a.2 + b.2)
}

#[inline]
fn vec3_dot(a: (f64, f64, f64), b: (f64, f64, f64)) -> f64 {
    a.0 * b.0 + a.1 * b.1 + a.2 * b.2
}

#[inline]
fn vec3_len(v: (f64, f64, f64)) -> f64 {
    (v.0 * v.0 + v.1 * v.1 + v.2 * v.2).sqrt()
}

#[inline]
fn vec3_scale(v: (f64, f64, f64), s: f64) -> (f64, f64, f64) {
    (v.0 * s, v.1 * s, v.2 * s)
}
