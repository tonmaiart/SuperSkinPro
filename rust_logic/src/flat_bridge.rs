//! Flat-array bridge operations for zero-copy Python ↔ Rust weight processing.
//!
//! These functions accept CSR (Compressed Sparse Row) flat arrays instead of
//! nested ``HashMap<i64, HashMap<i32, f64>>`` dicts.  The CSR layout eliminates
//! per-element PyO3 dictionary allocation overhead — three contiguous ``Vec<T>``
//! slices cross the FFI boundary as native C arrays.
//!
//! CSR Layout:
//!   vertex_offsets: ``Vec<u32>``   length = num_verts + 1
//!   bone_ids:       ``Vec<i32>``   length = total_weight_entries
//!   weights:        ``Vec<f64>``   length = total_weight_entries
//!
//! Mask Layout:
//!   mask_weights:   ``Vec<f64>``   length = num_verts
//!                                  sentinel = -1.0 means "no explicit value"

// ═════════════════════════════════════════════════════════════════════════
//  Flat mirror — mask-only mode
// ═════════════════════════════════════════════════════════════════════════

/// Flat-array mirror apply for mask-only mode.
///
/// Deliberately kept on the original raw coordinate-sign test (unlike
/// `mirror_logic::rust_mirror_apply`'s `target_side_mask`) — the
/// topology-based classification was confirmed to badly misclassify most of
/// a complex character mesh's mask coverage (only a small, simple region
/// like the feet came out right; gap-fill was silently papering over the
/// rest). The weight channel's classification fix stays; the mask channel
/// keeps this self-contained raw coordinate test — see
/// `features/mirror/README.md`'s guardrail: the two channels must never
/// share a side-classification helper again.
///
/// Returns `(mask_weights, gap_verts)` — `gap_verts` lists every target-side
/// vertex still at the "unset" sentinel after the nearest-vertex pass below
/// (e.g. asymmetric topology with no source match within `kd_tolerance`),
/// for the Python caller to fill via a BVH surface fallback (mirrors the
/// gap contract of `mirror_logic::rust_mirror_apply`, but computed from this
/// function's own local `is_target_side`, not any shared classification).
pub fn flat_mirror_apply_mask(
    mut mask_weights: Vec<f64>,
    vertex_coords: &[(f64, f64, f64)],
    axis: &str,
    direction: &str,
) -> (Vec<f64>, Vec<i64>) {
    let num_verts = mask_weights.len();
    let axis_idx = match axis {
        "X" => 0usize,
        "Y" => 1,
        "Z" => 2,
        _ => 1,
    };

    let is_source_side = |coord: &(f64, f64, f64)| -> bool {
        let val = [coord.0, coord.1, coord.2][axis_idx];
        let eps = 1e-5;
        if direction == "POS_NEG" {
            val >= -eps
        } else {
            val <= eps
        }
    };

    let is_target_side = |coord: &(f64, f64, f64)| -> bool {
        let val = [coord.0, coord.1, coord.2][axis_idx];
        let eps = 1e-5;
        if direction == "POS_NEG" {
            val < -eps
        } else {
            val > eps
        }
    };

    let kd_tolerance = 0.05f64;

    // STEP 1: Clear target side
    for v_idx in 0..num_verts {
        if v_idx >= vertex_coords.len() {
            break;
        }
        if is_target_side(&vertex_coords[v_idx]) {
            mask_weights[v_idx] = -1.0; // sentinel = clear
        }
    }

    // STEP 2: Mirror source → target
    let old_mask = mask_weights.clone();
    for v_idx in 0..num_verts {
        if v_idx >= vertex_coords.len() {
            break;
        }
        let coord = &vertex_coords[v_idx];
        if !is_source_side(coord) {
            continue;
        }
        let src_val = old_mask[v_idx];
        if src_val <= -0.5 {
            continue;
        }

        let mirrored = match axis_idx {
            0 => (-coord.0, coord.1, coord.2),
            1 => (coord.0, -coord.1, coord.2),
            _ => (coord.0, coord.1, -coord.2),
        };

        let mut best_tgt: Option<usize> = None;
        let mut best_dist = kd_tolerance;
        for tgt_idx in 0..num_verts {
            if tgt_idx >= vertex_coords.len() {
                break;
            }
            if !is_target_side(&vertex_coords[tgt_idx]) {
                continue;
            }
            let tc = &vertex_coords[tgt_idx];
            let dx = mirrored.0 - tc.0;
            let dy = mirrored.1 - tc.1;
            let dz = mirrored.2 - tc.2;
            let dist = (dx * dx + dy * dy + dz * dz).sqrt();
            if dist < best_dist {
                best_dist = dist;
                best_tgt = Some(tgt_idx);
            }
        }

        if let Some(tgt_v) = best_tgt {
            mask_weights[tgt_v] = src_val;
        }
    }

    // Gap detection: target-side vertices still at the "unset" sentinel.
    let mut gaps: Vec<i64> = Vec::new();
    for v_idx in 0..num_verts {
        if v_idx >= vertex_coords.len() {
            break;
        }
        if !is_target_side(&vertex_coords[v_idx]) {
            continue;
        }
        if mask_weights[v_idx] <= -0.5 {
            gaps.push(v_idx as i64);
        }
    }

    (mask_weights, gaps)
}

// ═════════════════════════════════════════════════════════════════════════
//  Flat visualizer — single-color ramp
// ═════════════════════════════════════════════════════════════════════════

/// Compute per-vertex RGB colors from CSR layer data in one flat pass.
/// Returns ``Vec<(f32, f32, f32)>`` of length *num_verts*.
pub fn flat_prepare_single_visualizer_colors(
    vertex_offsets: &[u32],
    bone_ids: &[i32],
    weights: &[f64],
    active_vg_id: i32,
    num_verts: usize,
) -> Vec<(f32, f32, f32)> {
    let stops: [(f32, [f32; 3]); 7] = [
        (0.00, [0.0, 0.0, 0.0]),
        (0.02, [0.0, 0.0, 1.0]),
        (0.25, [0.0, 1.0, 1.0]),
        (0.50, [0.0, 1.0, 0.0]),
        (0.72, [1.0, 1.0, 0.0]),
        (0.88, [1.0, 0.0, 0.0]),
        (1.00, [1.0, 1.0, 1.0]),
    ];

    let weight_to_rgb = |w: f32| -> (f32, f32, f32) {
        if w <= 0.0 {
            return (0.0, 0.0, 0.0);
        }
        if w >= 1.0 {
            return (1.0, 1.0, 1.0);
        }
        for i in 0..stops.len() - 1 {
            let (t0, c0) = stops[i];
            let (t1, c1) = stops[i + 1];
            if w >= t0 && w <= t1 {
                let frac = (w - t0) / (t1 - t0);
                return (
                    c0[0] + (c1[0] - c0[0]) * frac,
                    c0[1] + (c1[1] - c0[1]) * frac,
                    c0[2] + (c1[2] - c0[2]) * frac,
                );
            }
        }
        (1.0, 1.0, 1.0)
    };

    let mut colors = Vec::with_capacity(num_verts);
    for v_idx in 0..num_verts {
        let mut w: f32 = 0.0;
        if v_idx + 1 < vertex_offsets.len() {
            let start = vertex_offsets[v_idx] as usize;
            let end = vertex_offsets[v_idx + 1] as usize;
            let end = end.min(bone_ids.len()).min(weights.len());
            for i in start..end {
                if bone_ids[i] == active_vg_id {
                    w = weights[i] as f32;
                    break;
                }
            }
        }
        colors.push(weight_to_rgb(w));
    }
    colors
}

/// Compute per-vertex grayscale colors from flat mask array.
/// Returns ``Vec<(f32, f32, f32)>`` of length *num_verts*.
pub fn flat_prepare_mask_visualizer_colors(
    mask_weights: &[f64],
    mask_default: f64,
    num_verts: usize,
) -> Vec<(f32, f32, f32)> {
    let mut colors = Vec::with_capacity(num_verts);
    for i in 0..num_verts {
        let w = if i < mask_weights.len() && mask_weights[i] > -0.5 {
            mask_weights[i] as f32
        } else {
            mask_default as f32
        };
        let w = w.clamp(0.0, 1.0);
        colors.push((w, w, w));
    }
    colors
}
