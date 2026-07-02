"""Shared "closest point on surface" weight-transfer engine.

Used by both the live-mesh Copy Skin Weight operator (`ops.py`) and the JSON
import operator (`io_ops.py`) — importing a JSON file is conceptually the
same transfer, just with a "source" reconstructed from a file instead of a
live `bpy.types.Object`. A source only needs to supply, generically:

  - `composite_weights` / `composite_mask`: the flattened single-result
    `{v_idx: {bone_name: weight}}` / `{v_idx: mask_value}` pair used by
    `MERGE` (for a live mesh this is its native Vertex Groups; for a JSON
    file this is a `composite_weights` block captured at export time).
  - `layers`: a list of `(name, weight_dict, mask_dict, mask_default)`
    tuples used by `SEPARATE` — one entry per source SuperSkinPro Layer (or
    a single synthetic entry when there is no Layer system).
  - a `source_surface` — `(bvh, triangles, positions)` — needed only for
    `CLOSEST_DISTANCE`.
"""

from mathutils.bvhtree import BVHTree
from mathutils.interpolate import poly_3d_calc

from ...core.facade import CoreFacade
from ...interface.utils.utils import (
    _has_layer_system,
    _run_in_object_context,
    _select_only_layer,
    _enforce_visualizer_from_tab_state,
    sync_layers_to_ui_collection,
)


def unique_layer_name(existing_names, name):
    """Disambiguate *name* against *existing_names* with a Blender-style '.001' suffix."""
    if name not in existing_names:
        return name
    i = 1
    while f"{name}.{i:03d}" in existing_names:
        i += 1
    return f"{name}.{i:03d}"


def ensure_armature_modifier(target, armature_obj):
    """Create/find target's Armature modifier and point it at *armature_obj*.

    Shared by the live-mesh transfer (armature_obj = the source mesh's own
    bound armature) and JSON import's "Auto Assign Modifier" option
    (armature_obj = found-or-created by the name recorded at export time).
    """
    arm_mod = next((m for m in target.modifiers if m.type == 'ARMATURE'), None)
    if not arm_mod:
        arm_mod = target.modifiers.new(name="Armature", type='ARMATURE')
    arm_mod.object = armature_obj
    arm_mod.use_deform_preserve_volume = True
    return arm_mod


def ensure_native_vertex_groups(target, bone_names):
    """Create whichever of *bone_names* are missing from `target.vertex_groups`.

    Same auto-setup philosophy as auto-detecting/creating the Armature
    modifier: `finish()`'s reflatten always needs a slot to write into, even
    on a brand-new target or one with a partially-matching rig.
    """
    existing_vg_names = {vg.name for vg in target.vertex_groups}
    for name in bone_names:
        if name not in existing_vg_names:
            target.vertex_groups.new(name=name)


def build_surface(positions, triangles):
    """Build a world-space BVH from raw vertex positions + triangle index tuples.

    Purely geometric — independent of any Layer's weight data — so it should
    be built once per operator run and shared across every target/Layer.
    """
    bvh = BVHTree.FromPolygons(positions, triangles, all_triangles=True)
    return bvh, triangles, positions


def closest_surface_point_transfer(target, source_surface, layer_weights, layer_mask, mask_default):
    """True "closest point on surface" transfer (Maya's Closest Point / ngSkinTools'
    Transfer Weights): finds the nearest point on the source's triangulated surface
    for each target vertex and barycentric-blends the weight AND mask of that
    triangle's 3 vertices, using this Layer's own weight/mask data.

    This stays smooth wherever the source itself is smooth — unlike snapping to a
    single nearest vertex, which quantizes into flat, kinked bands whenever the
    target has more topology than the source — and it naturally confines a
    localized Layer's influence to wherever the source itself actually painted it,
    via the source's own mask values, instead of a separate distance-based falloff
    heuristic that doesn't know where the source's real paint boundary is.

    *mask_default* is used for any triangle vertex missing from *layer_mask* —
    a vertex not explicitly painted differently still carries the layer's own
    default mask level (typically 1.0 for a "filled white" layer), not 0.0.
    """
    bvh, tris, world_verts = source_surface
    matrix_world_tgt = target.matrix_world

    weight_map = {}
    mask_map = {}
    for v in target.data.vertices:
        P = matrix_world_tgt @ v.co
        location, _normal, tri_idx, _dist = bvh.find_nearest(P)
        if tri_idx is None:
            continue

        tri = tris[tri_idx]
        bary = poly_3d_calc([world_verts[i] for i in tri], location)

        bone_weights = {}
        mask_value = 0.0
        for w, v_idx in zip(bary, tri):
            mask_value += w * layer_mask.get(v_idx, mask_default)
            for bone, bw in layer_weights.get(v_idx, {}).items():
                bone_weights[bone] = bone_weights.get(bone, 0.0) + w * bw

        if mask_value <= 0.0 or not bone_weights:
            continue

        weight_map[v.index] = bone_weights
        mask_map[v.index] = mask_value

    return weight_map, mask_map


def compute_layer_payloads(
    layer_output, transfer_method, target, source_surface,
    composite_weights, composite_mask, layers, merge_name,
):
    """Shared MERGE/SEPARATE x CLOSEST_DISTANCE/VERTEX_ID decision tree.

    Returns a list of `(name, weight_dict, mask_dict)` triples ready for
    `write_layers_to_target()`, identically for a live-mesh source or a
    JSON-file source.
    """
    if layer_output == 'MERGE':
        if transfer_method == 'VERTEX_ID':
            weight_map = dict(composite_weights)
            mask_map = {v_idx: 1.0 for v_idx in weight_map}
        else:
            weight_map, mask_map = closest_surface_point_transfer(
                target, source_surface, composite_weights, composite_mask, 0.0,
            )
        return [(merge_name, weight_map, mask_map)]

    layer_payloads = []
    for name, layer_weights, layer_mask, mask_default in layers:
        if transfer_method == 'VERTEX_ID':
            # Source vertex index == target vertex index (checked by the caller),
            # so the layer's own dicts already ARE the target maps.
            layer_weight_map = {v_idx: bw for v_idx, bw in layer_weights.items() if bw}
            layer_mask_map = {v_idx: 1.0 for v_idx in layer_weight_map}
        else:
            layer_weight_map, layer_mask_map = closest_surface_point_transfer(
                target, source_surface, layer_weights, layer_mask, mask_default,
            )
        layer_payloads.append((name, layer_weight_map, layer_mask_map))
    return layer_payloads


def write_layers_to_target(context, target, insert_method, layer_payloads):
    """Create real SuperSkinPro Layer(s) on target and let finish() reflatten to native VGs."""
    facade = CoreFacade(context)
    ctrl = facade.get_ctrl()

    if not _has_layer_system(target):
        _run_in_object_context(context, ctrl.init_layer_system)
        CoreFacade.debug_log("feature_domains", f"weight_transfer: init_layer_system() on {target.name!r}")

    # For REPLACE, snapshot the pre-existing layers but do NOT remove them
    # yet — remove only after the new layer(s) already exist below. Some
    # layer systems refuse to remove the last remaining layer as a safety
    # rail; creating the replacements first means the target is never
    # left with zero layers, so that guard (if present) is never hit and
    # a full "replace everything" never gets stuck leaving one stale
    # layer behind. This requires no change to core/ at all.
    old_slots_to_remove = []
    existing_names = set()
    if insert_method == 'REPLACE':
        old_slots_to_remove = sorted(
            (m.get("index", -1) for m in facade.get_meta_list() if m.get("index", -1) >= 0),
            reverse=True,
        )
    else:
        existing_names = {m.get("name") for m in facade.get_meta_list() if m.get("name")}

    # create_layer() inserts each new Layer at the top of the stack, so
    # creating layer_payloads in its given order would land them in
    # reverse (last one created ends up on top, i.e. first). Creating
    # them back-to-front makes the *first* payload end up on top, which
    # matches the source's own stack order (e.g. Head, Arm, Base stays
    # Head, Arm, Base instead of coming out as Base, Arm, Head).
    last_slot = -1
    for name, weight_dict, mask_dict in reversed(layer_payloads):
        unique_name = unique_layer_name(existing_names, name)
        existing_names.add(unique_name)

        new_slot = _run_in_object_context(context, ctrl.create_layer, unique_name)
        CoreFacade.debug_log(
            "feature_domains",
            f"weight_transfer: create_layer(name={unique_name!r}) on {target.name!r} -> slot={new_slot} verts={len(weight_dict)}",
        )
        if new_slot is None or new_slot < 0:
            continue
        last_slot = new_slot
        facade.switch_to_layer(new_slot, push_undo=False)
        facade.write_layer_dict(weight_dict)
        if mask_dict:
            # A freshly created Layer has no mask coverage by default, so
            # every vertex reads as "outside the mask" (Mask Gap error)
            # even though weight data was written.
            facade.write_mask_dict(mask_dict)

    if old_slots_to_remove:
        for slot in old_slots_to_remove:
            _run_in_object_context(context, ctrl.remove_layer, slot)
        CoreFacade.debug_log(
            "feature_domains",
            f"weight_transfer: removed {len(old_slots_to_remove)} pre-existing layer(s) on {target.name!r} after creating replacements",
        )
        last_slot = ctrl.active_layer_index

    facade.finish()

    if last_slot >= 0:
        _select_only_layer(target, last_slot)
    sync_layers_to_ui_collection(target)
    _enforce_visualizer_from_tab_state(context)
