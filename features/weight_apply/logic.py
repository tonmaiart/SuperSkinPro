"""Weight-apply logic — Rust Accelerated Multi-OS Portal.

Merged from simple_ops_logic.py and smooth_logic.py.
Contains normalization helpers plus add, scale, sharpen, and smooth operations.

All functions operate on Integer Bone IDs. UIController guarantees int-keyed
dicts before these functions are invoked.
"""

from ...core.facade import CoreFacade


# ═══════════════════════════════════════════════════════════════════════════
#  Normalization helpers
# ═══════════════════════════════════════════════════════════════════════════

def normalize_around_active(v_weights, active_vg_id, locks, active_layer_idx=0):
    """Normalize so unlocked weights sum to 1.0 - lock_total using Integer Bone IDs.

    Args:
        v_weights: ``{bone_id: float}`` — mutable, updated in-place.
        active_vg_id: the integer bone ID that was just changed.
        locks: ``{bone_id: bool}`` — True when the group is locked.
        active_layer_idx: layer index (0 = base).
    """
    rust = CoreFacade.get_rust_gateway("norm_around_active")
    result = rust.call(
        "rust_norm_around_active",
        v_weights,
        active_vg_id,
        locks,
        active_layer_idx,
    )
    v_weights.clear()
    v_weights.update(result)
    return v_weights


def normalize_all_unlocked(v_weights, locks):
    """Scale every unlocked weight proportionally so they sum to 1.0 - lock_total."""
    rust = CoreFacade.get_rust_gateway("norm_all_unlocked")
    result = rust.call("rust_norm_all_unlocked", v_weights, locks)
    v_weights.clear()
    v_weights.update(result)
    return v_weights


# ═══════════════════════════════════════════════════════════════════════════
#  Add
# ═══════════════════════════════════════════════════════════════════════════

def apply_add(layer_dict, mask_dict, selected_verts, active_vg_id, intensity,
              vertex_groups_lock, active_layer_idx, is_mask_mode):
    """Add weight to the active bone on selected vertices using Integer Bone IDs."""
    rust = CoreFacade.get_rust_gateway("add_logic")
    return rust.call(
        "rust_add_logic",
        layer_dict,
        mask_dict,
        selected_verts,
        active_vg_id,
        intensity,
        vertex_groups_lock,
        active_layer_idx,
        is_mask_mode,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Scale
# ═══════════════════════════════════════════════════════════════════════════

def apply_scale(layer_dict, mask_dict, selected_verts, active_vg_id, intensity,
                vertex_groups_lock, is_mask_mode):
    """Scale the active bone weight on selected vertices using Integer Bone IDs."""
    rust = CoreFacade.get_rust_gateway("scale_logic")
    return rust.call(
        "rust_scale_logic",
        layer_dict,
        mask_dict,
        selected_verts,
        active_vg_id,
        intensity,
        vertex_groups_lock,
        is_mask_mode,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Sharpen
# ═══════════════════════════════════════════════════════════════════════════

def apply_sharpen(layer_dict, mask_dict, selected_verts, neighbors, active_vg_id,
                  intensity, is_mask_mode):
    """Sharpen the active bone weight on selected vertices using Integer Bone IDs."""
    rust = CoreFacade.get_rust_gateway("sharpen_logic")
    return rust.call(
        "rust_sharpen_logic",
        layer_dict,
        mask_dict,
        selected_verts,
        neighbors,
        active_vg_id,
        intensity,
        is_mask_mode,
    )


# ═══════════════════════════════════════════════════════════════════════════
#  Smooth
# ═══════════════════════════════════════════════════════════════════════════

def apply_smooth(layer_dict, mask_dict, selected_verts, neighbors, intensity,
                 vertex_groups_lock, affected_only, is_mask_mode):
    """Smooth weights across neighbouring vertices with Integer Bone ID core stability."""
    rust = CoreFacade.get_rust_gateway("smooth_logic")
    return rust.call(
        "rust_smooth_logic",
        layer_dict, mask_dict, selected_verts, neighbors,
        intensity, vertex_groups_lock, affected_only, is_mask_mode,
    )
