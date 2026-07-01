"""Layer list CRUD operators — add, remove, move, duplicate, merge, rename,
and per-row visibility toggle.

Relocated from operators/ops_layers_tool.py as part of the layer_viewer
domain extraction.
"""

import bpy

from ...core.facade import CoreFacade
from ...core_subsystems.license import LicenseService
from ...ui.utils import (
    _is_valid_mesh,
    _has_layer_system,
    _resolve_layer_target,
    _enforce_visualizer_from_tab_state,
    exit_mask_mode_if_active,
    sync_layers_to_ui_collection,
    _run_in_object_context,
    _select_only_layer,
)


# ==============================================================================
# LAYER LIST ROW OPERATORS
# ==============================================================================

class SUPERSKIN_OT_layer_toggle_visible_by_item(bpy.types.Operator):
    bl_idname = "superskin.layer_toggle_visible_by_item"
    bl_label = "Toggle Visibility from List"
    bl_options = {'INTERNAL', 'UNDO'}
    layer_index: bpy.props.IntProperty()

    def execute(self, context):
        obj = context.active_object
        if not _has_layer_system(obj):
            return {'CANCELLED'}

        _run_in_object_context(context, CoreFacade(context).get_ctrl().toggle_visible, self.layer_index)
        sync_layers_to_ui_collection(obj)
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


# ==============================================================================
# LAYER MANAGEMENT OPERATORS
# ==============================================================================

class SUPERSKIN_OT_layer_add(bpy.types.Operator):
    bl_idname = "superskin.layer_add"
    bl_label = "Add Weight Layer"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not _is_valid_mesh(obj):
            return {'CANCELLED'}

        ctrl = CoreFacade(context).get_ctrl()
        ctrl.init_layer_system()  # no-op if already initialised
        meta = ctrl.layer_meta_list()
        existing = len(meta)

        limit = LicenseService.layer_limit()
        if limit is not None and existing >= limit:
            self.report({'WARNING'},
                        f"Free version is limited to {limit} layers — activate a Pro "
                        f"license (Preferences > License) to add more")
            return {'CANCELLED'}

        new_idx = _run_in_object_context(context, ctrl.create_layer, f"Layer {existing}")
        _select_only_layer(obj, new_idx)
        sync_layers_to_ui_collection(obj)
        _enforce_visualizer_from_tab_state(context)
        return {'FINISHED'}


class SUPERSKIN_OT_layer_remove(bpy.types.Operator):
    bl_idname = "superskin.layer_remove"
    bl_label = "Remove Layer"
    bl_options = {'REGISTER', 'UNDO'}
    layer_index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        obj = context.active_object
        if not _has_layer_system(obj):
            return {'CANCELLED'}

        target = _resolve_layer_target(obj, self.layer_index)
        ctrl = CoreFacade(context).get_ctrl()
        if target < 0:
            target = ctrl.active_layer_index

        def _do_remove():
            exit_mask_mode_if_active(context, obj)
            ctrl.remove_layer(target)

        _run_in_object_context(context, _do_remove)
        _select_only_layer(obj, ctrl.active_layer_index)
        sync_layers_to_ui_collection(obj)
        _enforce_visualizer_from_tab_state(context)
        return {'FINISHED'}


class SUPERSKIN_OT_layer_move(bpy.types.Operator):
    bl_idname = "superskin.layer_move"
    bl_label = "Move Layer Up/Down"
    bl_options = {'INTERNAL', 'UNDO'}
    layer_index: bpy.props.IntProperty(default=-1)
    direction: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        obj = context.active_object
        if not _has_layer_system(obj):
            return {'CANCELLED'}

        target = _resolve_layer_target(obj, self.layer_index)
        ctrl = CoreFacade(context).get_ctrl()
        if target < 0:
            target = ctrl.active_layer_index

        moved = _run_in_object_context(context, ctrl.move_layer, target, self.direction)

        if moved:
            _select_only_layer(obj, target)
        sync_layers_to_ui_collection(obj)
        _enforce_visualizer_from_tab_state(context)

        if not moved:
            self.report({'INFO'}, "Layer is at stack boundary — cannot move further")
        return {'FINISHED'}


class SUPERSKIN_OT_layer_duplicate(bpy.types.Operator):
    bl_idname = "superskin.layer_duplicate"
    bl_label = "Duplicate Layer"
    bl_options = {'INTERNAL', 'UNDO'}
    layer_index: bpy.props.IntProperty(default=-1)

    def execute(self, context):
        obj = context.active_object
        if not _has_layer_system(obj):
            return {'CANCELLED'}

        target = _resolve_layer_target(obj, self.layer_index)
        ctrl = CoreFacade(context).get_ctrl()
        if target < 0:
            target = ctrl.active_layer_index

        limit = LicenseService.layer_limit()
        if limit is not None and len(ctrl.layer_meta_list()) >= limit:
            self.report({'WARNING'},
                        f"Free version is limited to {limit} layers — activate a Pro "
                        f"license (Preferences > License) to add more")
            return {'CANCELLED'}

        new_idx = _run_in_object_context(context, ctrl.duplicate_layer, target)
        if new_idx is not None and new_idx >= 0:
            _select_only_layer(obj, new_idx)
        sync_layers_to_ui_collection(obj)
        _enforce_visualizer_from_tab_state(context)
        return {'FINISHED'}


class SUPERSKIN_OT_layer_merge_selected(bpy.types.Operator):
    """Merge every currently multi-selected layer into the active one.

    Requires at least 2 layers selected via the Layers list multi-select
    pool (``layer_selected_indices``). Composites the selected subset
    top-down (same stack-order algorithm as a normal flatten), writes the
    result into the active layer's storage slot, and deletes the other
    selected layers. The button this is wired to is disabled (via
    ``poll()``) whenever fewer than 2 layers are selected.
    """
    bl_idname = "superskin.layer_merge_selected"
    bl_label = "Merge Selected Layers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not _has_layer_system(obj):
            return False
        raw = obj.superskin_storage.layer_selected_indices
        count = len([k for k in raw.split(",") if k]) if raw else 0
        return count >= 2

    def execute(self, context):
        obj = context.active_object
        raw = obj.superskin_storage.layer_selected_indices
        selected_indices = [int(k) for k in raw.split(",") if k]
        if len(selected_indices) < 2:
            self.report({'WARNING'}, "Select at least 2 layers to merge")
            return {'CANCELLED'}

        ctrl = CoreFacade(context).get_ctrl()
        target = ctrl.active_layer_index
        if target not in selected_indices:
            # Should not normally happen — on_single_select() always keeps
            # the active layer inside the selection pool after Item 2's
            # changes — but fall back defensively rather than crash.
            target = max(selected_indices)

        def _do_merge():
            exit_mask_mode_if_active(context, obj)
            return ctrl.merge_selected_layers(selected_indices, target)

        ok = _run_in_object_context(context, _do_merge)
        if not ok:
            self.report({'WARNING'}, "Merge failed — selection invalid")
            return {'CANCELLED'}

        _select_only_layer(obj, target)
        sync_layers_to_ui_collection(obj)
        _enforce_visualizer_from_tab_state(context)
        return {'FINISHED'}


class SUPERSKIN_OT_layer_rename_active(bpy.types.Operator):
    bl_idname = "superskin.layer_rename_active"
    bl_label = "Rename Active Layer"
    bl_options = {'REGISTER', 'UNDO'}
    new_name: bpy.props.StringProperty(name="Name", default="Layer")

    def execute(self, context):
        obj = context.active_object
        if not _has_layer_system(obj):
            return {'CANCELLED'}

        ctrl = CoreFacade(context).get_ctrl()
        ctrl.rename_layer(ctrl.active_layer_index, self.new_name)
        sync_layers_to_ui_collection(obj)
        return {'FINISHED'}

    def invoke(self, context, event):
        obj = context.active_object
        if not _has_layer_system(obj):
            return {'CANCELLED'}

        ctrl = CoreFacade(context).get_ctrl()
        self.new_name = ctrl.active_layer_name()
        return context.window_manager.invoke_props_dialog(self, width=250)

    def draw(self, context):
        self.layout.prop(self, "new_name", text="Name")


# ==============================================================================
# REGISTRATION
# ==============================================================================

_classes = (
    SUPERSKIN_OT_layer_toggle_visible_by_item,
    SUPERSKIN_OT_layer_add,
    SUPERSKIN_OT_layer_remove,
    SUPERSKIN_OT_layer_move,
    SUPERSKIN_OT_layer_duplicate,
    SUPERSKIN_OT_layer_merge_selected,
    SUPERSKIN_OT_layer_rename_active,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
