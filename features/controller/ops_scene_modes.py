"""Scene/edit-mode switching operators for SuperSkinPro.

Split out of ops_interface.py (2026-06) — everything here is about
entering/exiting/toggling Blender's interaction mode (Edit Mode, Pose Mode)
for the active mesh/armature, plus the viewport-gray-out theme dimming that
goes with it. Originally merged from interface/op_scene_modes.py.

Relocated from operators/ops_scene_modes.py to features/controller/ (2026-06).
"""

import bpy
import bmesh

from ...core.facade import CoreFacade
from ...core.bone_identity import BoneIdentityService
from ...interface.utils.utils import _is_valid_mesh

# Hoisted from function bodies — converted from absolute 'SuperSkinPro.*'
# imports to relative imports for Blender Extensions Platform compatibility.
from ...core.layer_storage.temp_vg_bridge import (
    has_temp_vgs, delete_temp_vgs, load_layer_to_temp_vgs,
    read_temp_vgs_from_bm,
)
from ...core.layer_storage.storage_service import LayerStorageService
from ...core.layer_storage.geometry import get_local_mapping
from ...interface.utils import utils as _utils
from ..bone_picker import deform_overlay


# ==============================================================================
# GLOBALS (from op_scene_modes.py)
# ==============================================================================

# Scene mode globals
_original_edge_wire = None
_original_wire_edit = None
_original_vertex = None


# ==============================================================================
# SCENE MODE HELPERS (from op_scene_modes.py)
# ==============================================================================

def _save_and_set_gray():
    global _original_edge_wire, _original_wire_edit, _original_vertex
    theme = bpy.context.preferences.themes[0].view_3d
    _original_edge_wire = tuple(theme.wire)
    _original_wire_edit = tuple(theme.wire_edit)
    _original_vertex = tuple(theme.vertex)
    theme.wire = (0.3, 0.3, 0.3)
    theme.wire_edit = (0.3, 0.3, 0.3)
    theme.vertex = (0.3, 0.3, 0.3)


def _restore_original_colors():
    global _original_edge_wire, _original_wire_edit, _original_vertex
    if _original_edge_wire is None:
        return
    theme = bpy.context.preferences.themes[0].view_3d
    theme.wire = _original_edge_wire
    theme.wire_edit = _original_wire_edit
    theme.vertex = _original_vertex


# ==============================================================================
# ENTER / EXIT / TOGGLE EDIT MODE (from op_scene_modes.py)
# ==============================================================================

def _enter_edit_mode(op, context):
    """Shared body for entering Edit Mode.

    Takes the invoking operator instance (`op`) so self.report() calls
    are attributed to whichever operator Blender actually invoked from
    the UI/keymap — calling this via a nested `bpy.ops.*()` from another
    operator's execute() would still log the report to the Info editor,
    but Blender suppresses the on-screen report banner for nested calls
    (see OBJECT_OT_mw_toggle_edit_mode, which calls this function directly
    instead of going through bpy.ops for exactly this reason).
    """
    target_mesh = None
    obj = context.active_object

    if obj:
        if obj.type == 'MESH':
            target_mesh = obj
        elif obj.type == 'ARMATURE':
            armature = obj
            context.scene["mw_last_active_armature"] = armature.name
            meshes = [o for o in context.view_layer.objects if o.type == 'MESH' and any(mod.type == 'ARMATURE' and mod.object == armature for mod in o.modifiers)]
            if meshes:
                cache_key = f"mw_last_mesh_{armature.name}"
                last_mesh_name = context.scene.get(cache_key, "")
                if last_mesh_name in context.view_layer.objects and context.view_layer.objects[last_mesh_name] in meshes:
                    target_mesh = context.view_layer.objects[last_mesh_name]
                else:
                    target_mesh = meshes[0]

    if not target_mesh:
        abs_mesh_name = context.scene.get("mw_absolute_last_mesh", "")
        if abs_mesh_name in context.view_layer.objects:
            target_mesh = context.view_layer.objects[abs_mesh_name]
        else:
            armatures = [o for o in context.view_layer.objects if o.type == 'ARMATURE']
            if armatures:
                last_arm_name = context.scene.get("mw_last_active_armature", "")
                armature = context.view_layer.objects.get(last_arm_name) if last_arm_name in context.view_layer.objects else armatures[0]
                meshes = [o for o in context.view_layer.objects if o.type == 'MESH' and any(mod.type == 'ARMATURE' and mod.object == armature for mod in o.modifiers)]
                if meshes:
                    target_mesh = meshes[0]
                    context.scene["mw_last_active_armature"] = armature.name

    if not target_mesh:
        op.report({'ERROR'}, "No Mesh or Armature found to enter Edit Mode.")
        return {'CANCELLED'}

    if not any(mod.type == 'ARMATURE' and mod.object for mod in target_mesh.modifiers):
        op.report({'WARNING'}, "This mesh has no Armature deformer.")
        return {'CANCELLED'}

    # ── Ensure the target can become the active object ──────────────
    if context.active_object != target_mesh:
        if context.active_object and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.select_all(action='DESELECT')
        # Make sure the target is selectable and visible
        target_mesh.hide_select = False
        target_mesh.hide_viewport = False
        target_mesh.hide_set(False)
        context.view_layer.objects.active = target_mesh
        target_mesh.select_set(True)
        # Verify the assignment took effect
        if context.active_object != target_mesh:
            op.report({'ERROR'}, f"Cannot set '{target_mesh.name}' as active object (it may be on a hidden collection or linked).")
            return {'CANCELLED'}

    obj = target_mesh

    for mod in obj.modifiers:
        if mod.type == 'ARMATURE':
            mod.show_in_editmode = True
            mod.show_on_cage = True

    # ── Auto-heal layer storage for topology changes ────────────
    try:
        CoreFacade(context).get_ctrl().heal_topology_if_needed()
    except Exception:
        pass  # non‑critical — the user can still paint

    # Orphan-bone *visibility* in the Deform Bones list no longer depends
    # on this call — orphan rows are read from obj.superskin_bones_collection
    # (a mirror CollectionProperty kept current by
    # ui.utils.sync_bones_to_ui_collection via the depsgraph_update_post /
    # load_post handlers, through BoneIdentityService.get_scan_for_object's
    # signature-gated read-only scan_readonly()) that recomputes itself
    # automatically whenever vertex-group names, layer data, or the
    # armature's bone set actually changed. This call's only remaining job
    # is refreshing the bone-UUID map (a mesh-data write, which Blender
    # forbids from inside draw() — see bone_identity_service.py's
    # docstring) so the orphan resolver can keep suggesting "RENAMED"
    # targets; it's not required for orphan rows to appear at all.
    try:
        BoneIdentityService(context).backfill_and_scan()
    except Exception:
        pass  # graceful — the UUID-backed rename suggestion is optional

    if obj.mode != 'EDIT':
        if context.active_object is None:
            op.report({'ERROR'}, "No active object – cannot enter Edit Mode.")
            return {'CANCELLED'}
        bpy.ops.object.mode_set(mode='EDIT')

    # Load active layer into temp VGs for native BMesh undo tracking.
    # Guard the OBJECT bounce so the auto-save handler does not schedule a
    # spurious bake timer while temp VGs are being initialised.
    _was_suppressing = context.scene.superskin_internal_transaction
    context.scene.superskin_internal_transaction = True
    try:
        bpy.ops.object.mode_set(mode='OBJECT')
        _load_active_layer_to_temp_vgs(obj, context)
        bpy.ops.object.mode_set(mode='EDIT')
    finally:
        context.scene.superskin_internal_transaction = _was_suppressing

    bpy.ops.mesh.select_mode(type='VERT')

    saved = context.scene.get(f"mw_saved_selection_{obj.name}", [])
    if saved:
        if context.active_object is None:
            op.report({'ERROR'}, "Lost active object while restoring selection.")
            return {'CANCELLED'}
        bpy.ops.object.mode_set(mode='OBJECT')
        for v in obj.data.vertices:
            v.select = v.index in saved
        bpy.ops.object.mode_set(mode='EDIT')

    overlay = context.space_data.overlay
    overlay.show_weight = True
    overlay.show_edge_bevel_weight = False
    overlay.show_edge_crease = False
    overlay.show_edge_seams = False
    overlay.show_edge_sharp = False
    overlay.show_faces = False
    if hasattr(overlay, "show_vertex_group_weights"):
        overlay.show_vertex_group_weights = True

    bpy.ops.wm.tool_set_by_id(name="builtin.select_circle")

    _save_and_set_gray()

    # Auto-enable the custom weight visualizer (mask-row-aware)
    is_mask = getattr(context.scene, "superskin_is_mask_mode", False)
    viz_mode = 'MASK' if is_mask else 'SINGLE'
    try:
        CoreFacade(context).get_ctrl().set_visualizer_mode(viz_mode)
    except Exception:
        pass  # graceful — visualizer is optional

    try:
        deform_overlay.show()
    except Exception:
        pass

    try:
        _utils.force_open_super_skin_tab()
    except Exception:
        pass

    return {'FINISHED'}


class OBJECT_OT_mw_enter_edit_mode(bpy.types.Operator):
    bl_idname = "object.mw_enter_edit_mode"
    bl_label = "Enter Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return _enter_edit_mode(self, context)


def _exit_edit_mode(op, context, *, keep_panel_open: bool = False):
    """Shared body for exiting Edit Mode — see `_enter_edit_mode` docstring
    for why callers must invoke this directly instead of nesting through
    `bpy.ops.object.mw_exit_edit_mode()`.

    keep_panel_open: when True, skips force_close_tab() so the sidebar
    remains visible after returning to Object Mode (used by Save Weights
    and the auto-save guard, which both want the panel to stay open).
    """
    obj = context.active_object
    if not _is_valid_mesh(obj):
        return {'CANCELLED'}

    _restore_original_colors()

    # Bake temp VGs → ss_layer_N before leaving Edit Mode
    _bake_temp_vgs_on_exit(obj)

    # Clean up the custom visualizer before leaving edit mode.
    try:
        CoreFacade(context).get_ctrl().set_visualizer_mode('CLEAR')
    except Exception:
        pass

    # Also hide the deform bone overlay — it's Edit-Mode-only and should
    # never carry over into Object Mode.
    try:
        deform_overlay.hide()
    except Exception:
        pass

    bpy.ops.object.mode_set(mode='OBJECT')

    # Delete temp VGs in Object Mode as required by delete_temp_vgs contract.
    try:
        if has_temp_vgs(obj):
            delete_temp_vgs(obj)
    except Exception:
        pass

    selected_indices = [v.index for v in obj.data.vertices if v.select]
    context.scene[f"mw_saved_selection_{obj.name}"] = selected_indices
    context.scene["mw_absolute_last_mesh"] = obj.name

    for mod in obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object:
            context.scene[f"mw_last_mesh_{mod.object.name}"] = obj.name
            context.scene["mw_last_active_armature"] = mod.object.name

    overlay = context.space_data.overlay
    overlay.show_weight = False
    overlay.show_edge_bevel_weight = True
    overlay.show_edge_crease = True
    overlay.show_edge_seams = True
    overlay.show_edge_sharp = True
    overlay.show_faces = True
    if hasattr(overlay, "show_vertex_group_weights"):
        overlay.show_vertex_group_weights = False

    if not keep_panel_open:
        _utils.force_close_tab()
    return {'FINISHED'}


class OBJECT_OT_mw_exit_edit_mode(bpy.types.Operator):
    bl_idname = "object.mw_exit_edit_mode"
    bl_label = "Exit Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        return _exit_edit_mode(self, context)


class OBJECT_OT_mw_toggle_edit_mode(bpy.types.Operator):
    bl_idname = "object.mw_toggle_edit_mode"
    bl_label = "Toggle Edit Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj and obj.mode == 'EDIT':
            return _exit_edit_mode(self, context)
        else:
            return _enter_edit_mode(self, context)


class OBJECT_OT_mw_force_pose_mode(bpy.types.Operator):
    """Force switch to Pose Mode, or toggle back to Object Mode if already in Pose Mode"""
    bl_idname = "object.mw_force_pose_mode"
    bl_label = "Force Pose Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object

        if obj and obj.type == 'ARMATURE' and obj.mode == 'POSE':
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}

        # ── Enter Pose Mode ──
        if obj and obj.type == 'ARMATURE':
            context.scene["mw_last_active_armature"] = obj.name

        armature_name = context.scene.get("mw_last_active_armature", "")

        if not armature_name and obj and obj.type == 'MESH':
            for mod in obj.modifiers:
                if mod.type == 'ARMATURE' and mod.object:
                    armature_name = mod.object.name
                    context.scene["mw_last_active_armature"] = armature_name
                    break

        if not armature_name or armature_name not in context.view_layer.objects:
            self.report({'WARNING'}, "No previous Armature found in cache or modifiers.")
            return {'CANCELLED'}

        if obj and obj.type == 'MESH' and obj.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
            selected_indices = [v.index for v in obj.data.vertices if v.select]
            context.scene[f"mw_saved_selection_{obj.name}"] = selected_indices

            overlay = context.space_data.overlay
            overlay.show_weight = False
            overlay.show_edge_bevel_weight = True
            overlay.show_edge_crease = True
            overlay.show_edge_seams = True
            overlay.show_edge_sharp = True
            overlay.show_faces = True

        if context.active_object and context.active_object.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        armature = context.view_layer.objects[armature_name]
        bpy.ops.object.select_all(action='DESELECT')
        context.view_layer.objects.active = armature
        armature.select_set(True)

        bpy.ops.object.mode_set(mode='POSE')

        _utils.force_close_tab()
        return {'FINISHED'}


# ==============================================================================
# TEMP VG HELPERS
# ==============================================================================

def _load_active_layer_to_temp_vgs(obj, context):
    """Load the active layer into temp VGs after entering Edit Mode."""
    try:
        if has_temp_vgs(obj):
            delete_temp_vgs(obj)

        storage = LayerStorageService(obj.data)
        if not storage.has_layer_system():
            return

        active_idx = storage.get_active_layer_index()
        layer_dict = storage.read_layer_dict(active_idx)
        mask_dict = storage.read_mask_dict(active_idx)
        _, id_to_bone = get_local_mapping(obj)

        load_layer_to_temp_vgs(obj, layer_dict, mask_dict, active_idx, id_to_bone)
    except Exception as e:
        print(f"[SuperSkinPro] Warning: could not load temp VGs: {e}")


def _bake_temp_vgs_on_exit(obj):
    """Bake temp VGs back to ss_layer_N when exiting Edit Mode.
    Caller must delete temp VGs in OBJECT mode after mode_set."""
    try:

        if not has_temp_vgs(obj):
            return

        bm = bmesh.from_edit_mesh(obj.data)
        layer_dict, mask_dict, active_idx = read_temp_vgs_from_bm(bm, obj)
        storage = LayerStorageService(obj.data)
        storage.write_layer_dict(active_idx, layer_dict)
        if mask_dict:
            storage.write_mask_dict(active_idx, mask_dict)
    except Exception as e:
        print(f"[SuperSkinPro] Warning: could not bake temp VGs on exit: {e}")


# ==============================================================================
# MODE-GATE OPERATORS  (UI buttons "Edit Layer Weight" / "Save Weights")
# ==============================================================================

class SUPERSKIN_OT_enter_layer_edit(bpy.types.Operator):
    """Enter Edit Mode and prepare the active layer for weight painting."""
    bl_idname = "superskin.enter_layer_edit"
    bl_label = "Edit Layer Weight"
    bl_description = "Enter Edit Mode to paint weights on the active layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == 'MESH' and context.mode == 'OBJECT')

    def execute(self, context):
        obj = context.active_object
        if obj and obj.type == 'MESH' and "ss_layers_meta" not in obj.data:
            try:
                CoreFacade(context).get_ctrl().init_layer_system()
            except Exception as exc:
                self.report({'ERROR'}, f"Layer system init failed: {exc}")
                return {'CANCELLED'}
        return _enter_edit_mode(self, context)


class SUPERSKIN_OT_save_weights(bpy.types.Operator):
    """Bake weight changes back to the active layer and return to Object Mode."""
    bl_idname = "superskin.save_weights"
    bl_label = "Save Weights"
    bl_description = "Save weight edits to the active layer and exit to Object Mode"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        return bool(obj and obj.type == 'MESH' and context.mode == 'EDIT_MESH')

    def execute(self, context):
        result = _exit_edit_mode(self, context, keep_panel_open=True)
        if result == {'FINISHED'}:
            try:
                CoreFacade(context).finish(color_only=False)
            except Exception as exc:
                print(f"[SuperSkinPro] Save Weights: finish() failed: {exc}")
        return result


# ==============================================================================
# AUTO-SAVE GUARD — bakes temp VGs when user exits Edit Mode via Tab/keymap
# without clicking "Save Weights". Uses depsgraph_update_post to detect the
# unguarded EDIT_MESH → non-EDIT transition.
# ==============================================================================

_mode_guard_last_mode: dict = {}  # {obj_name: mode_string}


@bpy.app.handlers.persistent
def _superskin_auto_save_guard(scene, depsgraph):
    """Detect unguarded Edit-Mode exits and trigger an auto-bake."""
    ctx = bpy.context
    if not ctx:
        return
    obj = ctx.active_object
    if not (obj and obj.type == 'MESH'):
        _mode_guard_last_mode.clear()
        return

    current_mode = ctx.mode
    last_mode = _mode_guard_last_mode.get(obj.name, current_mode)
    _mode_guard_last_mode[obj.name] = current_mode

    if (last_mode == 'EDIT_MESH'
            and current_mode != 'EDIT_MESH'
            and not scene.superskin_internal_transaction):
        try:
            if has_temp_vgs(obj):
                _schedule_auto_save(obj.name)
        except Exception:
            pass


def _schedule_auto_save(obj_name: str) -> None:
    """Register a one-shot timer that bakes temp VGs after an unguarded exit.

    Blender serializes the BMesh (including __ssp_* temp VG weights) back to
    mesh.vertices when Tab is pressed, so re-entering Edit Mode in the timer
    creates a fresh BMesh with the correct weights — making read_temp_vgs_from_bm
    reliable even though the user has already exited.
    """
    def _do_auto_save():
        _ctx = bpy.context
        if not _ctx:
            return None
        _obj = _ctx.view_layer.objects.get(obj_name)
        if not (_obj and _obj.type == 'MESH'):
            return None

        if not has_temp_vgs(_obj):
            return None

        _restore_original_colors()

        _scene = _ctx.scene
        _prev_flag = _scene.superskin_internal_transaction
        _scene.superskin_internal_transaction = True
        try:
            if _ctx.active_object != _obj:
                _ctx.view_layer.objects.active = _obj
            if _obj.mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
            # Re-enter Edit Mode so bmesh.from_edit_mesh can read temp VG weights.
            bpy.ops.object.mode_set(mode='EDIT')
            _bake_temp_vgs_on_exit(_obj)
            try:
                CoreFacade(_ctx).get_ctrl().set_visualizer_mode('CLEAR')
            except Exception:
                pass
            try:
                deform_overlay.hide()
            except Exception:
                pass
            bpy.ops.object.mode_set(mode='OBJECT')
            if has_temp_vgs(_obj):
                delete_temp_vgs(_obj)
        except Exception as exc:
            print(f"[SuperSkinPro] Auto-save guard bake failed: {exc}")
        finally:
            _scene.superskin_internal_transaction = _prev_flag
        return None

    bpy.app.timers.register(_do_auto_save, first_interval=0.0)


# ==============================================================================
# REGISTRATION
# ==============================================================================

_classes = (
    OBJECT_OT_mw_enter_edit_mode,
    OBJECT_OT_mw_exit_edit_mode,
    OBJECT_OT_mw_toggle_edit_mode,
    OBJECT_OT_mw_force_pose_mode,
    SUPERSKIN_OT_enter_layer_edit,
    SUPERSKIN_OT_save_weights,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.app.handlers.depsgraph_update_post.append(_superskin_auto_save_guard)


def unregister():
    try:
        bpy.app.handlers.depsgraph_update_post.remove(_superskin_auto_save_guard)
    except Exception:
        pass
    _mode_guard_last_mode.clear()
    _restore_original_colors()
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)