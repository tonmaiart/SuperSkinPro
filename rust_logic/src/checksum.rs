use std::collections::HashMap;

/// Compute a deterministic checksum of real on-mesh deform weights.
/// Mirrors the Python vanilla algorithm structurally for consistent
/// internal Rust-vs-Rust comparisons across undo/redo boundaries.
///
/// Input: {v_idx: {vg_idx: weight}} — same shape as the existing
/// nested-dict layer format used elsewhere in this codebase.
pub fn deform_checksum_engine(deform_data: &HashMap<usize, HashMap<i32, f64>>) -> u32 {
    let mut h: u64 = 0;
    let mut v_indices: Vec<&usize> = deform_data.keys().collect();
    v_indices.sort();

    for &v_idx in v_indices {
        let groups = &deform_data[&v_idx];
        let mut g_indices: Vec<&i32> = groups.keys().collect();
        g_indices.sort();

        for &g_idx in g_indices {
            let weight = groups[&g_idx];
            let rounded = (weight * 100000.0).round() / 100000.0; // round to 5 decimals
            // Mix v_idx, g_idx, and rounded weight into a deterministic hash
            // using a simple FNV-ish mixing scheme. Exact cross-language
            // compatibility with Python's hash() is not required since the
            // checksum is only compared against values from the same code path.
            let mixed = (v_idx as u64)
                .wrapping_mul(2654435761)
                .wrapping_add(g_idx as u64)
                .wrapping_mul(2246822519)
                .wrapping_add(rounded.to_bits());
            // No `& 0xFFFFFFFF` here — masking every iteration discards the
            // upper 32 bits of `mixed` (which carry the sign/exponent/top
            // mantissa bits of the weight's f64 representation) before they
            // can ever influence the hash. Any weight whose lower 32 bits
            // happen to be zero in IEEE-754 (true for "clean" values like
            // 0.5, 1.0, 0.25, 2.0 — extremely common in practice) then
            // contributes nothing, so two different weights on the same
            // (v_idx, g_idx) collide to the same checksum. Let `h` carry
            // the full 64 bits of state across iterations instead.
            h = h.wrapping_mul(1000003).wrapping_add(mixed);
        }
    }

    // Fold the upper half into the lower half so high-bit-only differences
    // (e.g. between two round floats) still affect the truncated u32 — a
    // bare `h as u32` would silently re-introduce the same collision bug
    // for the last-mixed entry.
    (h ^ (h >> 32)) as u32
}
