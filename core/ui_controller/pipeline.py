"""Pipeline finalisation — reflatten, save/restore, topology heal, context checks.

Every function takes the UIController instance as its first parameter (``ctrl``).
Pure conversion helpers live in core_subsystems/layer_pipeline.py.
"""

import json
import bmesh
from ...core_subsystems.layer_compositor import LayerCompositor


def finish(ctrl, *, color_only: bool = False):
    """Flatten visible layers to the mesh, invalidate caches, and redraw.

    Routes through ``bmesh.from_edit_mesh()`` when the object is in EDIT
    mode so that Vertex Group writes land directly on the edit-bmesh
    without a costly mode round-trip.

    Args:
        color_only: When True, the colour VBO cache is invalidated directly
            and the structural wireframe/point/colour batches are left to
            self-detect staleness via the deform-generation bump below —
            cheaper than a full invalidate, but still correct for weight
            ops that reshape the mesh. Use for weight-paint strokes where
            mesh *topology* (vert/edge/face counts) hasn't changed.
    """
    in_edit = ctrl.obj.mode == 'EDIT'
    if in_edit:
        flatten_to_mesh_edit(ctrl)
    else:
        ctrl.storage.flatten_visible_layers_to_mesh(ctrl.obj)
    ctrl.mesh.update()
    ctrl.obj.update_tag()
    # Real Vertex Group weights just changed, which reshapes the
    # Armature-evaluated mesh at the CURRENT frame — frame_current alone
    # (the visualizer's other staleness signal) can't see that. Bump
    # unconditionally (cheap int increment) so BoneMode/MaskMode's
    # topo/deform cache key self-detects the shape change next draw,
    # even on the color_only fast path.
    ctrl.shader_mgr.bump_deform_generation()
    # Bump an object-level counter so the multi_color_preview draw callback
    # can detect mesh shape changes without importing from core.
    ctrl.obj["__ssp_deform_gen"] = ctrl.obj.get("__ssp_deform_gen", 0) + 1
    if color_only:
        ctrl.shader_mgr.invalidate_color_only()
    else:
        ctrl.shader_mgr.invalidate_and_redraw()
    # In Edit Mode, real VG weights were written to the BMesh. The native
    # Blender weight overlay reads from the BMesh but only refreshes when
    # VIEW_3D areas receive a redraw request — mesh.update() alone is
    # insufficient. Tag all 3D viewports so the overlay updates immediately.
    if in_edit:
        import bpy as _bpy
        for window in _bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == 'VIEW_3D':
                    area.tag_redraw()


def flatten_to_mesh(ctrl):
    ctrl.storage.flatten_visible_layers_to_mesh(ctrl.obj)


def flatten_to_mesh_edit(ctrl):
    """Write composited layer weights directly through the edit-bmesh.

    In Edit Mode, the active layer lives in temp VGs (__ssp_*).
    Other layers still live in ss_layer_N.
    This function composites all of them correctly.
    """
    from ..layer_storage.temp_vg_bridge import (
        has_temp_vgs, read_temp_vgs_from_bm
    )
    from ...core_subsystems.layer_compositor import LayerCompositor as _LC_local

    mesh = ctrl.mesh
    if "ss_layers_meta" not in mesh:
        return

    vg_list = ctrl.obj.vertex_groups
    num_verts = len(mesh.vertices)
    if num_verts == 0 or len(vg_list) == 0:
        return

    meta = json.loads(mesh.get("ss_layers_meta", "[]"))
    idx_to_name = {vg.index: vg.name for vg in vg_list
                   if not vg.name.startswith("__ssp_")}

    active_idx = ctrl.storage.get_active_layer_index()

    layer_data_map = {}
    mask_data_map = {}

    for layer in meta:
        l_idx = layer["index"]
        if l_idx == active_idx:
            continue
        raw = mesh.get(f"ss_layer_{l_idx}")
        if raw:
            layer_data_map[l_idx] = raw
        raw_mask = mesh.get(f"ss_mask_{l_idx}")
        if raw_mask:
            mask_data_map[l_idx] = raw_mask

    if has_temp_vgs(ctrl.obj):
        # Read directly from the active edit BMesh's deform layer.
        # update_from_editmode() does not reliably sync VG weights to
        # mesh.vertices during Edit Mode operations, so reading from the
        # BMesh directly guarantees that weight ops (which write via
        # write_layer_to_temp_vgs_bm) are visible here immediately.
        bm_active = bmesh.from_edit_mesh(mesh)
        layer_dict, mask_dict, _ = read_temp_vgs_from_bm(bm_active, ctrl.obj)
        layer_data_map[active_idx] = _LC_local.encode(layer_dict)
        if mask_dict:
            mask_data_map[active_idx] = _LC_local.encode(mask_dict)
    else:
        raw = mesh.get(f"ss_layer_{active_idx}")
        if raw:
            layer_data_map[active_idx] = raw
        raw_mask = mesh.get(f"ss_mask_{active_idx}")
        if raw_mask:
            mask_data_map[active_idx] = raw_mask

    result = LayerCompositor.composite_layers(meta, layer_data_map, mask_data_map,
                                               idx_to_name, num_verts)

    bm = bmesh.from_edit_mesh(mesh)
    bm.verts.ensure_lookup_table()
    deform = bm.verts.layers.deform.verify()

    name_to_idx = {vg.name: vg.index for vg in vg_list
                   if not vg.name.startswith("__ssp_")}

    old_state: dict = {}
    for bv in bm.verts:
        v_deform = bv[deform]
        if v_deform:
            filtered = {g_idx: w for g_idx, w in v_deform.items()
                        if g_idx in idx_to_name}
            if filtered:
                old_state[bv.index] = filtered

    new_state = LayerCompositor.bone_weights_to_deform_state(result, name_to_idx)

    all_affected = set(old_state.keys()) | set(new_state.keys())
    for v_idx in all_affected:
        old = old_state.get(v_idx, {})
        new = new_state.get(v_idx, {})
        if old == new:
            continue
        bv = bm.verts[v_idx]
        v_deform = bv[deform]
        for g_idx in list(v_deform.keys()):
            if g_idx in idx_to_name and g_idx not in new:
                del v_deform[g_idx]
        for g_idx, w in new.items():
            v_deform[g_idx] = w

    bmesh.update_edit_mesh(mesh)


def save_current_layer_state(ctrl):
    idx = ctrl.active_layer_index
    meta = ctrl.storage.read_meta_list()

    sel = getattr(ctrl.obj.superskin_storage, "selected_names", ",")
    meta = ctrl._layer_mgr.set_selected_bones(meta, idx, sel)

    active_idx = ctrl.obj.superskin_storage.last_clicked_index
    active_name = ""
    if 0 <= active_idx < len(ctrl.obj.vertex_groups):
        active_name = ctrl.obj.vertex_groups[active_idx].name
    meta = ctrl._layer_mgr.set_active_bone_name(meta, idx, active_name)
    ctrl.storage.write_meta_list(meta)


def restore_layer_state(ctrl):
    meta = ctrl.storage.read_meta_list()
    idx = ctrl.active_layer_index

    locks = ctrl._layer_mgr.get_bone_locks(meta, idx)
    for item in ctrl.obj.superskin_bones_collection:
        item.lock_weight = locks.get(item.name, False)

    sel = ctrl._layer_mgr.get_selected_bones(meta, idx)
    if sel and hasattr(ctrl.obj, "superskin_storage"):
        ctrl.obj.superskin_storage.selected_names = sel

    name = ctrl._layer_mgr.get_active_bone_name(meta, idx)
    if name and name in ctrl.obj.vertex_groups:
        ctrl.obj.superskin_storage.last_clicked_index = ctrl.obj.vertex_groups[name].index


def is_mask_context(ctrl) -> bool:
    try:
        scene = ctrl.ctx.scene
        if getattr(scene, "superskin_is_mask_mode", False):
            return True
        if getattr(scene, "superskin_skin_sub_tabs", False):
            return True
        return False
    except Exception:
        return False


def heal_topology_if_needed(ctrl) -> bool:
    """Auto-heal layer/mask storage after topology edits, reflattening
    if anything changed. Returns True if healing did anything."""
    healed = ctrl.storage.heal_new_vertices(ctrl.obj)
    if healed:
        ctrl.storage.flatten_visible_layers_to_mesh(ctrl.obj)
        ctrl.mesh.update()
        ctrl.obj.update_tag()
    return healed
