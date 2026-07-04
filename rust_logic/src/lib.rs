use pyo3::prelude::*;
use pyo3::types::PyModule;
use std::collections::{HashMap, HashSet};

// ── 📁 Sub-modules ──────────────────────────────────────────────────────
mod auto_logic;
mod bone_analyzer;
mod checksum;
mod flat_bridge;
mod layer_compositor;
mod license_logic;
mod mirror_logic;
mod norm;
mod simple_ops_logic;
mod smooth_logic;
mod visualizer;

// Bone data structure for spatial processing
#[derive(Debug, Clone)]
pub struct BoneRaw {
    pub name: String,
    pub head: [f32; 3],
    pub tail: [f32; 3],
}

// Helper: parse Python tuple inputs into Rust BoneRaw vectors
fn parse_py_inputs(py_inputs: Vec<(String, (f32, f32, f32), (f32, f32, f32))>) -> Vec<BoneRaw> {
    py_inputs
        .into_iter()
        .map(|(name, h, t)| BoneRaw {
            name,
            head: [h.0, h.1, h.2],
            tail: [t.0, t.1, t.2],
        })
        .collect()
}

// ==============================================================================
// 🧠 SECTION 1: BONE ANALYZER PORTALS (string-based — bone names only)
// ==============================================================================

#[pyfunction]
fn rust_compute_bone_display_order(
    py_inputs: Vec<(String, (f32, f32, f32), (f32, f32, f32))>,
) -> PyResult<Vec<String>> {
    let bone_raw_data = parse_py_inputs(py_inputs);
    Ok(bone_analyzer::compute_bone_order(&bone_raw_data))
}

#[pyfunction]
fn rust_compute_bone_depths(
    py_inputs: Vec<(String, (f32, f32, f32), (f32, f32, f32))>,
) -> PyResult<HashMap<String, usize>> {
    let bone_raw_data = parse_py_inputs(py_inputs);
    Ok(bone_analyzer::compute_bone_depths(&bone_raw_data))
}

// ==============================================================================
// 🧪 SECTION 2: WEIGHT CALCULATOR & COMPOSITOR PORTALS
// ⚡ Local ID Mapping: bone weights use i32 (vertex-group index) keys in
//    the hot-path calculator functions. Display/compositor functions keep
//    String keys since they're cold-path.
// ==============================================================================

#[pyfunction]
#[pyo3(signature = (meta_clean, layer_decoded_map, mask_decoded_map, num_verts, dirty_verts=None))]
fn rust_composite_layers(
    meta_clean: Vec<HashMap<String, f32>>,
    // Compositor: keeps String keys for shader display (cold path)
    layer_decoded_map: HashMap<usize, HashMap<usize, HashMap<String, f32>>>,
    mask_decoded_map: HashMap<usize, HashMap<usize, f32>>,
    num_verts: usize,
    // Optional vertex subset for hot paths (e.g. the weight-apply gesture
    // modal) that know exactly which vertices could have changed since the
    // last call. `None` preserves the original full-mesh behavior exactly --
    // see layer_compositor.rs's composite_layers_engine() doc comment.
    dirty_verts: Option<Vec<usize>>,
) -> PyResult<HashMap<usize, HashMap<String, f32>>> {
    let result = layer_compositor::composite_layers_engine(
        meta_clean,
        layer_decoded_map,
        mask_decoded_map,
        num_verts,
        dirty_verts,
    );
    Ok(result)
}

/// Flat-array (COO) variant of `rust_composite_layers`, added as a NEW
/// function name (never renaming/removing `rust_composite_layers` itself,
/// per project convention) so the Python side can detect availability via
/// `hasattr()` and fall back to the original HashMap-based call against an
/// older `rust_logic.so` that hasn't been rebuilt with this function yet.
///
/// `coo_*_map` are four parallel per-layer maps (all keyed by the same
/// layer index) instead of one `HashMap<usize, (Vec<...>, ...)>` of tuples,
/// to keep each individual PyO3 conversion path simple and predictable:
///   coo_vert_ids_map:   {layer_idx: [vertex_idx, ...]}
///   coo_bone_ids_map:   {layer_idx: [local_bone_id, ...]}   (same length as vert_ids)
///   coo_weights_map:    {layer_idx: [weight, ...]}          (same length as vert_ids)
///   coo_id_to_bone_map: {layer_idx: {local_bone_id: bone_name}}
/// `dict_layer_data_map` carries any layers NOT converted to COO (in
/// practice, just the tiny active layer on the weight-apply gesture's hot
/// path) in the original `HashMap<usize, HashMap<String,f32>>` per-vertex
/// shape. See `core_subsystems/layer_compositor/codec.py` for how these are
/// built, and `layer_compositor.rs::composite_layers_engine_mixed()` for how
/// they're merged and handed to the existing, unmodified compositing math.
#[pyfunction]
#[pyo3(signature = (meta_clean, dict_layer_data_map, coo_vert_ids_map, coo_bone_ids_map,
                    coo_weights_map, coo_id_to_bone_map, mask_decoded_map, num_verts,
                    dirty_verts=None))]
fn rust_composite_layers_mixed(
    meta_clean: Vec<HashMap<String, f32>>,
    dict_layer_data_map: HashMap<usize, HashMap<usize, HashMap<String, f32>>>,
    coo_vert_ids_map: HashMap<usize, Vec<u32>>,
    coo_bone_ids_map: HashMap<usize, Vec<i32>>,
    coo_weights_map: HashMap<usize, Vec<f64>>,
    coo_id_to_bone_map: HashMap<usize, HashMap<i32, String>>,
    mask_decoded_map: HashMap<usize, HashMap<usize, f32>>,
    num_verts: usize,
    dirty_verts: Option<Vec<usize>>,
) -> PyResult<HashMap<usize, HashMap<String, f32>>> {
    let result = layer_compositor::composite_layers_engine_mixed(
        meta_clean,
        dict_layer_data_map,
        coo_vert_ids_map,
        coo_bone_ids_map,
        coo_weights_map,
        coo_id_to_bone_map,
        mask_decoded_map,
        num_verts,
        dirty_verts,
    );
    Ok(result)
}

#[pyfunction]
fn rust_smooth_logic(
    layer_dict: HashMap<usize, HashMap<i32, f64>>,
    mask_dict: HashMap<usize, f64>,
    selected_verts: Vec<usize>,
    neighbors: HashMap<usize, Vec<usize>>,
    intensity: f64,
    vertex_groups_lock: HashMap<i32, bool>,
    affected_only: bool,
    is_mask_mode: bool,
) -> PyResult<(HashMap<usize, HashMap<i32, f64>>, HashMap<usize, f64>)> {
    let (res_layer, res_mask) = smooth_logic::apply_smooth_engine(
        layer_dict,
        mask_dict,
        selected_verts,
        neighbors,
        intensity,
        vertex_groups_lock,
        affected_only,
        is_mask_mode,
    );
    Ok((res_layer, res_mask))
}

// ==============================================================================
// 🧪 SECTION 3: WEIGHT CALCULATOR — NORM / ADD / SCALE / SHARPEN / AUTO / MIRROR
// ⚡ Int-ID pipeline for all hot-path calculators
// ==============================================================================

#[pyfunction]
fn rust_norm_around_active(
    v_weights: HashMap<i32, f64>,
    active_vg_id: i32,
    locks: HashMap<i32, bool>,
    active_layer_idx: i64,
) -> PyResult<HashMap<i32, f64>> {
    norm::rust_normalize_around_active(v_weights, active_vg_id, locks, active_layer_idx)
}

#[pyfunction]
fn rust_norm_all_unlocked(
    v_weights: HashMap<i32, f64>,
    locks: HashMap<i32, bool>,
) -> PyResult<HashMap<i32, f64>> {
    norm::rust_normalize_all_unlocked(v_weights, locks)
}

// ── Checksum ─────────────────────────────────────────────────────────

#[pyfunction]
fn rust_deform_checksum(
    deform_data: HashMap<usize, HashMap<i32, f64>>,
) -> PyResult<u32> {
    Ok(checksum::deform_checksum_engine(&deform_data))
}

// ── Add ─────────────────────────────────────────────────────────────

#[pyfunction]
fn rust_add_logic(
    layer_dict: HashMap<i64, HashMap<i32, f64>>,
    mask_dict: HashMap<i64, f64>,
    selected_verts: Vec<i64>,
    active_vg_id: i32,
    intensity: f64,
    locks: HashMap<i32, bool>,
    #[allow(unused_variables)] active_layer_idx: i64,
    is_mask_mode: bool,
) -> PyResult<(HashMap<i64, HashMap<i32, f64>>, HashMap<i64, f64>)> {
    // Delegate to simple_ops_logic module
    simple_ops_logic::rust_add_logic(
        layer_dict, mask_dict, selected_verts,
        active_vg_id, intensity, locks,
        active_layer_idx, is_mask_mode,
    )
}

// ── Scale ───────────────────────────────────────────────────────────

#[pyfunction]
fn rust_scale_logic(
    layer_dict: HashMap<i64, HashMap<i32, f64>>,
    mask_dict: HashMap<i64, f64>,
    selected_verts: Vec<i64>,
    active_vg_id: i32,
    intensity: f64,
    locks: HashMap<i32, bool>,
    is_mask_mode: bool,
) -> PyResult<(HashMap<i64, HashMap<i32, f64>>, HashMap<i64, f64>)> {
    simple_ops_logic::rust_scale_logic(
        layer_dict, mask_dict, selected_verts,
        active_vg_id, intensity, locks, is_mask_mode,
    )
}

// ── Sharpen ─────────────────────────────────────────────────────────

#[pyfunction]
fn rust_sharpen_logic(
    layer_dict: HashMap<i64, HashMap<i32, f64>>,
    mask_dict: HashMap<i64, f64>,
    selected_verts: Vec<i64>,
    neighbors: HashMap<i64, Vec<i64>>,
    active_vg_id: i32,
    intensity: f64,
    is_mask_mode: bool,
) -> PyResult<(HashMap<i64, HashMap<i32, f64>>, HashMap<i64, f64>)> {
    simple_ops_logic::rust_sharpen_logic(
        layer_dict, mask_dict, selected_verts,
        neighbors, active_vg_id, intensity, is_mask_mode,
    )
}

// ── Auto (string-based — bone name matching required) ────────────────

#[pyfunction]
fn rust_auto_logic(
    selected_verts: Vec<i64>,
    vertex_world_coords: Vec<(f64, f64, f64)>,
    bone_data: Vec<(String, (f64, f64, f64), (f64, f64, f64))>,
    bone_name_to_name: HashMap<String, String>,
    hit_count_map: HashMap<i64, HashMap<String, i64>>,
) -> PyResult<HashMap<i64, String>> {
    auto_logic::rust_auto_logic(
        selected_verts, vertex_world_coords,
        bone_data, bone_name_to_name, hit_count_map,
    )
}

// ── Mirror ──────────────────────────────────────────────────────────

#[pyfunction]
fn rust_mirror_generate_pairs(
    vg_names: Vec<String>,
    bone_centers: HashMap<String, (f64, f64, f64)>,
    sr_list: Vec<(String, String)>,
    axis: String,
    direction: String,
) -> PyResult<HashMap<String, String>> {
    mirror_logic::rust_mirror_generate_pairs(
        vg_names, bone_centers, sr_list, axis, direction,
    )
}

#[pyfunction]
fn rust_mirror_apply(
    layer_dict: HashMap<i64, HashMap<i32, f64>>,
    id_pairs: HashMap<i32, i32>,
    vertex_groups_lock: HashMap<i32, bool>,
    vertex_coords: Vec<(f64, f64, f64)>,
    target_side_mask: Vec<bool>,
    axis: String,
    direction: String,
) -> PyResult<(HashMap<i64, HashMap<i32, f64>>, Vec<i64>)> {
    mirror_logic::rust_mirror_apply(
        layer_dict, id_pairs, vertex_groups_lock,
        vertex_coords, target_side_mask, axis, direction,
    )
}

#[pyfunction]
fn rust_mirror_apply_mask(
    mask_dict: HashMap<i64, f64>,
    vertex_coords: Vec<(f64, f64, f64)>,
    axis: String,
    direction: String,
) -> PyResult<HashMap<i64, f64>> {
    mirror_logic::rust_mirror_apply_mask(
        mask_dict, vertex_coords, axis, direction,
    )
}

// ── Visualizer & Scanner (⚡ Int-ID pipeline) ─────────────────────────

#[pyfunction]
fn rust_get_visible_influence_bones(
    layer_dict: HashMap<usize, HashMap<i32, f32>>,
) -> PyResult<HashSet<i32>> {
    Ok(visualizer::get_visible_influence_bones(layer_dict))
}

// ── Flat-Bridge (CSR arrays — zero-copy FFI) ────────────────────────

#[pyfunction]
fn rust_mirror_apply_mask_flat(
    mask_weights: Vec<f64>,
    vertex_coords: Vec<(f64, f64, f64)>,
    axis: String,
    direction: String,
) -> PyResult<(Vec<f64>, Vec<i64>)> {
    Ok(flat_bridge::flat_mirror_apply_mask(
        mask_weights, &vertex_coords, &axis, &direction,
    ))
}

#[pyfunction]
fn rust_prepare_single_visualizer_colors_flat(
    vertex_offsets: Vec<u32>,
    bone_ids: Vec<i32>,
    weights: Vec<f64>,
    active_vg_id: i32,
    num_verts: usize,
) -> PyResult<Vec<(f32, f32, f32)>> {
    Ok(flat_bridge::flat_prepare_single_visualizer_colors(
        &vertex_offsets, &bone_ids, &weights,
        active_vg_id, num_verts,
    ))
}

#[pyfunction]
fn rust_prepare_mask_visualizer_colors_flat(
    mask_weights: Vec<f64>,
    mask_default: f64,
    num_verts: usize,
) -> PyResult<Vec<(f32, f32, f32)>> {
    Ok(flat_bridge::flat_prepare_mask_visualizer_colors(
        &mask_weights, mask_default, num_verts,
    ))
}

// ── License (Gumroad activation — HTTPS + HMAC-signed offline re-check) ─────

#[pyfunction]
fn rust_verify_gumroad_license(
    license_key: String,
    product_id: String,
) -> PyResult<(bool, String, String)> {
    Ok(license_logic::verify_gumroad_license(license_key, product_id))
}

#[pyfunction]
fn rust_check_cached_activation(license_key: String, token: String) -> PyResult<bool> {
    Ok(license_logic::check_cached_activation(license_key, token))
}

// ── All Function Register ───────────────────────────────────────────

#[pymodule]
fn rust_logic<'py>(_py: Python<'py>, m: &Bound<'py, PyModule>) -> PyResult<()> {
    // Bone Analyzer
    m.add_function(wrap_pyfunction!(rust_compute_bone_display_order, m)?)?;
    m.add_function(wrap_pyfunction!(rust_compute_bone_depths, m)?)?;

    // Weight Calculator — compositor + smooth
    m.add_function(wrap_pyfunction!(rust_composite_layers, m)?)?;
    m.add_function(wrap_pyfunction!(rust_composite_layers_mixed, m)?)?;
    m.add_function(wrap_pyfunction!(rust_smooth_logic, m)?)?;

    // Weight Calculator — norm
    m.add_function(wrap_pyfunction!(rust_norm_around_active, m)?)?;
    m.add_function(wrap_pyfunction!(rust_norm_all_unlocked, m)?)?;

    // Checksum
    m.add_function(wrap_pyfunction!(rust_deform_checksum, m)?)?;

    // Weight Calculator — add / scale / sharpen / auto / mirror
    m.add_function(wrap_pyfunction!(rust_add_logic, m)?)?;
    m.add_function(wrap_pyfunction!(rust_scale_logic, m)?)?;
    m.add_function(wrap_pyfunction!(rust_sharpen_logic, m)?)?;
    m.add_function(wrap_pyfunction!(rust_auto_logic, m)?)?;
    m.add_function(wrap_pyfunction!(
        rust_mirror_generate_pairs,
        m
    )?)?;
    m.add_function(wrap_pyfunction!(rust_mirror_apply, m)?)?;
    m.add_function(wrap_pyfunction!(rust_mirror_apply_mask, m)?)?;

    // Visualizer
    m.add_function(wrap_pyfunction!(rust_get_visible_influence_bones, m)?)?;

    // Flat-Bridge (CSR arrays — zero-copy FFI)
    m.add_function(wrap_pyfunction!(rust_mirror_apply_mask_flat, m)?)?;
    m.add_function(wrap_pyfunction!(rust_prepare_single_visualizer_colors_flat, m)?)?;
    m.add_function(wrap_pyfunction!(rust_prepare_mask_visualizer_colors_flat, m)?)?;

    // License
    m.add_function(wrap_pyfunction!(rust_verify_gumroad_license, m)?)?;
    m.add_function(wrap_pyfunction!(rust_check_cached_activation, m)?)?;
    Ok(())
}
