"""Mirror-weight logic — Rust Accelerated Multi-OS Portal.

Combines name-pair generation with the layer-aware mirror operation.

⚡ LOCAL ID MAPPING:
- ``generate_pairs`` remains string-based (pattern matching needs bone names)
- ``apply`` and ``apply_mask`` use Integer Bone IDs for inner layer_dict keys
"""

from ...core.facade import CoreFacade


def get_bone_centers(core_facade):
    """Compute world-space bone centre positions keyed by vertex-group name.

    Replaces the UIController._bone_centers escape hatch — parametrized over
    CoreFacade so that core/ui_controller/ carries no feature-specific logic.
    """
    obj = core_facade.get_obj()
    arm_obj = next(
        (m.object for m in obj.modifiers if m.type == 'ARMATURE' and m.object), None
    )
    centers = {}
    arm_mat = arm_obj.matrix_world if arm_obj else None
    for vg in core_facade.get_vertex_groups():
        if arm_obj and arm_mat:
            bone = arm_obj.data.bones.get(vg.name)
            if bone:
                centers[vg.name] = (
                    arm_mat @ ((bone.head_local + bone.tail_local) * 0.5)
                ).to_tuple()
                continue
        centers[vg.name] = None
    return centers


def _is_source_side(coord, axis_idx, direction):
    eps = 1e-5
    val = coord[axis_idx]
    if direction == 'POS_NEG':
        return val >= -eps
    return val <= eps


def _is_target_side(coord, axis_idx, direction):
    eps = 1e-5
    if direction == 'POS_NEG':
        return coord[axis_idx] < -eps
    return coord[axis_idx] > eps


def generate_pairs(vg_names, bone_centers, sr_list, axis, direction):
    """Build mirror name pairs from search/replace rules (string-based)."""
    rust = CoreFacade.get_rust_gateway("mirror_generate_pairs")
    result = rust.call(
        "rust_mirror_generate_pairs",
        vg_names,
        bone_centers,
        sr_list,
        axis,
        direction,
    )
    return {str(k): str(v) for k, v in result.items()}


def apply(layer_dict, id_pairs, vertex_groups_lock, vertex_coords, axis, direction):
    """Layer-aware mirror with centre-plane splitting operating on Integer Bone IDs.

    All bone references are already integer vertex-group indices when they
    arrive here — UIController converted name_pairs→id_pairs upstream.

    Args:
        layer_dict: ``{v_idx: {bone_id: weight}}`` (int→int→float)
        id_pairs: ``{src_bone_id: tgt_bone_id}``
        vertex_groups_lock: ``{bone_id: bool}``
    """
    if not id_pairs:
        return layer_dict

    layer_dict = {k: dict(v) for k, v in layer_dict.items()}

    rust = CoreFacade.get_rust_gateway("mirror_apply")
    result = rust.call(
        "rust_mirror_apply",
        layer_dict,
        id_pairs,
        vertex_groups_lock,
        vertex_coords,
        axis,
        direction,
    )
    return {int(k): dict(v) for k, v in result.items()}


def apply_mask(mask_dict, vertex_coords, axis, direction):
    """Mirror mask values across axis — no bone dimension.

    Args:
        mask_dict: ``{v_idx: float}``
    """
    rust = CoreFacade.get_rust_gateway("mirror_apply_mask")
    result = rust.call(
        "rust_mirror_apply_mask",
        mask_dict,
        vertex_coords,
        axis,
        direction,
    )
    return {k: v for k, v in result.items()}


def apply_mask_flat(mask_dict: dict, vertex_coords: list,
                    axis: str, direction: str,
                    num_verts: int) -> dict:
    """⚡ Zero-copy flat-array mirror mask via CSR bridge.

    Returns ``mask_dict`` (int-keyed dict).
    """
    rust = CoreFacade.get_rust_gateway("mirror_apply_mask_flat")
    _bridge = CoreFacade.get_flat_array_bridge()
    mask_flat = _bridge.mask_to_flat(mask_dict, num_verts, sentinel=_bridge.MASK_SENTINEL)
    res_mask_flat = rust.call(
        "rust_mirror_apply_mask_flat",
        mask_flat, vertex_coords, axis, direction,
    )
    return _bridge.flat_to_mask(res_mask_flat, sentinel=_bridge.MASK_SENTINEL)


def build_layer_mirror_plan(core_facade, axis, direction, sr_raw):
    """Resolve VG name pairs -> int ID pairs for the mirror computation.

    Returns None when no matching pairs exist (caller skips the layer channel).
    """
    name_pairs = generate_pairs(
        vg_names=[vg.name for vg in core_facade.get_vertex_groups()],
        bone_centers=get_bone_centers(core_facade),
        sr_list=sr_raw,
        axis=axis,
        direction=direction,
    )
    if not name_pairs:
        return None

    bone_to_id, id_to_bone = core_facade.get_unified_mapping()
    id_pairs = {
        bone_to_id[src]: bone_to_id[tgt]
        for src, tgt in name_pairs.items()
        if src in bone_to_id and tgt in bone_to_id
    }
    return id_pairs if id_pairs else None


def execute_mirror_pipeline(core_facade):
    """Full mirror pipeline via CoreFacade only — no UIController dependency.

    Raises ValueError when neither channel can produce output, allowing the
    domain to return CANCELLED without an unhandled exception.
    """
    from .mirror_feature import MirrorPreferencesService

    axis = MirrorPreferencesService.get_mirror_axis()
    direction = MirrorPreferencesService.get_mirror_direction()
    sr_raw = MirrorPreferencesService.get_mirror_search_replace_pairs()
    is_mask = core_facade.is_mask_context()
    both_data = MirrorPreferencesService.get_mirror_both_data()

    do_mask = is_mask or both_data
    do_layer = (not is_mask) or both_data

    if do_layer:
        id_pairs = build_layer_mirror_plan(core_facade, axis, direction, sr_raw)
        if id_pairs is None:
            do_layer = False

    if not do_mask and not do_layer:
        raise ValueError("No mirror pairs found for either channel.")

    if do_mask:
        res_mask = apply_mask_flat(
            mask_dict=core_facade.get_active_mask_dict(),
            vertex_coords=core_facade.get_vertex_coordinates(),
            axis=axis,
            direction=direction,
            num_verts=core_facade.get_num_verts(),
        )
        core_facade.write_mask_dict(res_mask)

    if do_layer:
        # read_active_layer() caches the unified mapping for the write call.
        layer_str = core_facade.read_active_layer()
        bone_to_id, id_to_bone = core_facade.get_unified_mapping()

        layer_int = {
            int(v_idx): {
                int(bone_to_id[b]): float(w)
                for b, w in weights.items()
                if b in bone_to_id
            }
            for v_idx, weights in layer_str.items()
        }
        res_layer_int = apply(
            layer_dict=layer_int,
            id_pairs=id_pairs,
            vertex_groups_lock=core_facade.get_locks_by_id(),
            vertex_coords=core_facade.get_vertex_coordinates(),
            axis=axis,
            direction=direction,
        )
        res_layer_str = {
            int(v_idx): {
                str(id_to_bone[b_id]): float(w)
                for b_id, w in weights.items()
                if b_id in id_to_bone
            }
            for v_idx, weights in res_layer_int.items()
        }
        # write_active_layer calls finish() internally — no explicit finish needed.
        core_facade.write_active_layer(res_layer_str)
    else:
        # Mask-only path: write_mask_dict does not call finish.
        core_facade.finish_color_only()
