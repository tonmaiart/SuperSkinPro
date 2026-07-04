use std::collections::HashMap;

/// Top-down alpha-blend compositor — the sole implementation of SuperSkinPro's
/// layer stack flattening (no Python fallback; see core/rust_loader.py).
///
/// `meta_list` arrives already reordered bottom-to-top by the Python caller
/// (`compositor.py::composite_layers`) — the first entry processed here is
/// the foundation (`is_base == true`) layer.
///
/// Dispatches to one of two implementations depending on `dirty_verts`:
/// - `None` (the default, used by every caller except the weight-apply
///   gesture hot path): `composite_layers_full`, byte-identical to this
///   function's original single-path implementation (dense `Vec` indexed
///   0..num_verts) -- unchanged behavior and performance for every existing
///   caller (Save Weight, layer merge, mirror, clipboard, etc.).
/// - `Some(verts)`: `composite_layers_subset`, which only visits the given
///   vertex indices, using a sparse `HashMap` instead of a dense
///   `num_verts`-sized `Vec`. Safe to use ONLY when the caller can guarantee
///   every vertex whose composited result could have changed since the last
///   call is included in `verts` -- see core/ui_controller/pipeline.py's
///   flatten_to_mesh_edit() docstring for the exact contract.
pub fn composite_layers_engine(
    meta_list: Vec<HashMap<String, f32>>,
    layer_data_map: HashMap<usize, HashMap<usize, HashMap<String, f32>>>,
    mask_data_map: HashMap<usize, HashMap<usize, f32>>,
    num_verts: usize,
    dirty_verts: Option<Vec<usize>>,
) -> HashMap<usize, HashMap<String, f32>> {
    match dirty_verts {
        None => composite_layers_full(meta_list, layer_data_map, mask_data_map, num_verts),
        Some(verts) => composite_layers_subset(meta_list, layer_data_map, mask_data_map, &verts),
    }
}

/// Original full-mesh implementation, unchanged from before `dirty_verts`
/// was introduced. See `composite_layers_engine`'s doc comment for the
/// per-step algorithm description (base layer / overlay layers / final
/// renormalize pass) -- identical here, just extracted into its own
/// function name.
fn composite_layers_full(
    meta_list: Vec<HashMap<String, f32>>,
    layer_data_map: HashMap<usize, HashMap<usize, HashMap<String, f32>>>,
    mask_data_map: HashMap<usize, HashMap<usize, f32>>,
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

/// Reconstructs one layer's `{vertex: {bone_name: weight}}` map from a
/// sparse COO (coordinate-list) representation -- three parallel arrays
/// (`vert_ids`, `bone_ids`, `weights`, all the same length, one entry per
/// vertex-bone weight pair) plus a small per-layer `id_to_bone` lookup
/// table mapping this call's local integer bone IDs back to bone-name
/// strings. This exists so the FFI boundary only has to marshal numeric
/// arrays (cheap) plus one small string table per layer (tens of bone
/// names, not thousands of vertex-weight entries), instead of a
/// `HashMap<usize, HashMap<String, f32>>` with a Python string object per
/// weight entry.
///
/// IMPORTANT (matches the "vertex absent from the dict" semantics that
/// `composite_layers_full`/`composite_layers_subset` already depend on for
/// their is_base clear-on-absence behavior): a vertex that never appears in
/// `vert_ids` must be ABSENT from the returned map (so `.get()` yields
/// `None`), never present with an empty inner `HashMap`. This function only
/// ever calls `.entry(v_idx)` when actually processing a real COO row for
/// that vertex, so a vertex with zero rows is never inserted at all --
/// absence is preserved by construction, not by an explicit empty-check.
fn coo_layer_to_hashmap(
    vert_ids: &[u32],
    bone_ids: &[i32],
    weights: &[f64],
    id_to_bone: &HashMap<i32, String>,
) -> HashMap<usize, HashMap<String, f32>> {
    let mut result: HashMap<usize, HashMap<String, f32>> = HashMap::new();
    let n = vert_ids.len();
    for i in 0..n {
        let v_idx = vert_ids[i] as usize;
        let bone_id = bone_ids[i];
        let w = weights[i] as f32;
        if let Some(bone_name) = id_to_bone.get(&bone_id) {
            result
                .entry(v_idx)
                .or_insert_with(HashMap::new)
                .insert(bone_name.clone(), w);
        }
    }
    result
}

/// Entry point for the flat-array (COO) FFI path. Converts every
/// COO-encoded non-active layer back into the same
/// `HashMap<usize, HashMap<String, f32>>` shape the existing
/// `composite_layers_engine` already expects per layer, merges those with
/// any layers that arrived as plain dicts (typically just the tiny active
/// layer on the weight-apply gesture's hot path -- see
/// `core_subsystems/layer_compositor/codec.py`), then delegates to the
/// EXISTING, UNMODIFIED `composite_layers_engine` for the actual
/// alpha-blend math. This function only changes how per-layer input data
/// crosses the FFI boundary; it does not touch the compositing algorithm,
/// the dense/sparse (`dirty_verts`) dispatch, or any of their correctness
/// guarantees.
pub fn composite_layers_engine_mixed(
    meta_list: Vec<HashMap<String, f32>>,
    dict_layer_data_map: HashMap<usize, HashMap<usize, HashMap<String, f32>>>,
    coo_vert_ids_map: HashMap<usize, Vec<u32>>,
    coo_bone_ids_map: HashMap<usize, Vec<i32>>,
    coo_weights_map: HashMap<usize, Vec<f64>>,
    coo_id_to_bone_map: HashMap<usize, HashMap<i32, String>>,
    mask_data_map: HashMap<usize, HashMap<usize, f32>>,
    num_verts: usize,
    dirty_verts: Option<Vec<usize>>,
) -> HashMap<usize, HashMap<String, f32>> {
    let mut combined_layer_data_map = dict_layer_data_map;

    for (l_idx, vert_ids) in &coo_vert_ids_map {
        // Each of these four maps is populated together, per layer, by the
        // same Python-side harvest loop -- a missing companion entry for a
        // layer index that IS present in coo_vert_ids_map would be a
        // caller-side bug, not something to silently paper over, so `.get()`
        // here uses an empty fallback only to stay panic-safe against that
        // caller bug rather than to represent a legitimate empty layer.
        let empty_bone_ids: Vec<i32> = Vec::new();
        let empty_weights: Vec<f64> = Vec::new();
        let empty_id_to_bone: HashMap<i32, String> = HashMap::new();
        let bone_ids = coo_bone_ids_map.get(l_idx).unwrap_or(&empty_bone_ids);
        let weights = coo_weights_map.get(l_idx).unwrap_or(&empty_weights);
        let id_to_bone = coo_id_to_bone_map.get(l_idx).unwrap_or(&empty_id_to_bone);

        let converted = coo_layer_to_hashmap(vert_ids, bone_ids, weights, id_to_bone);
        combined_layer_data_map.insert(*l_idx, converted);
    }

    composite_layers_engine(
        meta_list,
        combined_layer_data_map,
        mask_data_map,
        num_verts,
        dirty_verts,
    )
}

/// Vertex-subset implementation. Same per-vertex math as
/// `composite_layers_full`, restricted to `verts` instead of `0..num_verts`,
/// using a sparse `HashMap` accumulator instead of a dense `num_verts`-sized
/// `Vec` so cost scales with `verts.len()`, not the whole mesh.
fn composite_layers_subset(
    meta_list: Vec<HashMap<String, f32>>,
    layer_data_map: HashMap<usize, HashMap<usize, HashMap<String, f32>>>,
    mask_data_map: HashMap<usize, HashMap<usize, f32>>,
    verts: &[usize],
) -> HashMap<usize, HashMap<String, f32>> {
    let mut accumulated: HashMap<usize, HashMap<String, f32>> = HashMap::new();

    for layer_meta in &meta_list {
        let l_idx = *layer_meta.get("index").unwrap_or(&0.0) as usize;
        let mask_default = *layer_meta.get("mask_default").unwrap_or(&1.0);

        let layer_dict = match layer_data_map.get(&l_idx) {
            Some(d) => d,
            None => continue,
        };

        let mask_dict = mask_data_map.get(&l_idx);
        let is_base = layer_meta.get("is_base").map_or(false, |&v| v > 0.5);

        for &v_idx in verts {
            let mut v_mask = match mask_dict {
                Some(md) => *md.get(&v_idx).unwrap_or(&mask_default),
                None => mask_default,
            };
            v_mask = v_mask.clamp(0.0, 1.0);

            let vw = match layer_dict.get(&v_idx) {
                Some(w) => w,
                None => {
                    if is_base {
                        accumulated.remove(&v_idx);
                    }
                    continue;
                }
            };

            let entry = accumulated.entry(v_idx).or_insert_with(HashMap::new);

            if is_base {
                entry.clear();
                for (bone_name, &w) in vw {
                    entry.insert(bone_name.clone(), w * v_mask);
                }
            } else {
                if vw.is_empty() || v_mask <= 0.0001 {
                    continue;
                }
                let above_total: f32 = vw.values().sum();
                if above_total <= 0.0001 {
                    continue;
                }

                for w_accum in entry.values_mut() {
                    *w_accum *= 1.0 - v_mask;
                }

                let inv_above = 1.0 / above_total;
                for (bone_name, &w_raw) in vw {
                    let w_norm = w_raw * inv_above;
                    let e = entry.entry(bone_name.clone()).or_insert(0.0);
                    *e += w_norm * v_mask;
                }
            }
        }
    }

    let mut result: HashMap<usize, HashMap<String, f32>> = HashMap::new();
    for &v_idx in verts {
        let bone_weights = match accumulated.get(&v_idx) {
            Some(bw) => bw,
            None => continue,
        };
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
