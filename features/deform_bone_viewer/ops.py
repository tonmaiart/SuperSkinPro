"""Deform Bone Viewer operators — per-row bone lock toggle, select all,
vertex selection by influence, Show Affecting Bones popup, and influence
popup menus.

Relocated from operators/ops_layers_tool.py (bone list operators) and
operators/ops_bones_tool.py (vertex selection, bone inspection, and popup
influence menu). ops_bones_tool.py has been removed entirely.
"""

import bpy
import bmesh

from ...core.facade import CoreFacade
from ...interface.utils.utils import _is_valid_mesh

# Hoisted from function bodies — converted from absolute 'SuperSkinPro.*'
# imports to relative imports for Blender Extensions Platform compatibility.
from ...core_subsystems.layer_manager.layer_manager import (
    clear_all_selected, add_vg_selected,
)
from ...core.layer_storage.temp_vg_bridge import (
    read_temp_vgs_to_layer, delete_temp_vgs,
)
from ...core.layer_storage.storage_service import LayerStorageService


# ==============================================================================
# BONE LIST OPERATORS
# ==============================================================================

class SUPERSKIN_OT_toggle_vg_lock(bpy.types.Operator):
    bl_idname = "superskin.toggle_vg_lock"
    bl_label = "Toggle Vertex Group Lock"
    bl_options = {'INTERNAL', 'UNDO'}

    index: bpy.props.IntProperty()
    vg_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.active_object
        if not obj:
            return {'CANCELLED'}

        vg_list = obj.vertex_groups
        if self.index < 0 or self.index >= len(vg_list):
            return {'CANCELLED'}

        ctrl = CoreFacade(context).get_ctrl()

        # Read current state from metadata — metadata is the single source of
        # truth for bone locks, not the native VertexGroup.lock_weight field.
        current_locks = ctrl.get_bone_locks()
        clicked_name = self.vg_name
        new_lock_state = not current_locks.get(clicked_name, False)

        new_locks = dict(current_locks)
        if f",{clicked_name}," in obj.superskin_storage.selected_names:
            for item in obj.superskin_bones_collection:
                if f",{item.name}," in obj.superskin_storage.selected_names:
                    new_locks[item.name] = new_lock_state
        else:
            new_locks[clicked_name] = new_lock_state

        ctrl.set_bone_locks(new_locks)

        # Sync the UI mirror collection so draw_extra_icon reflects the new
        # state immediately — without this, tag_redraw redraws stale values.
        for item in obj.superskin_bones_collection:
            item.lock_weight = new_locks.get(item.name, False)

        context.area.tag_redraw()
        return {'FINISHED'}


class SUPERSKIN_OT_select_all_vgs(bpy.types.Operator):
    bl_idname = "superskin.select_all_vgs"
    bl_label = "Select All Visible Influences"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        obj = context.active_object
        if not obj or not obj.vertex_groups:
            return {'CANCELLED'}

        storage = obj.superskin_storage
        all_names = ",".join([vg.name for vg in obj.vertex_groups])
        storage.selected_names = f",{all_names},"

        # Persist selection to the active layer
        try:
            ctrl = CoreFacade(context).get_ctrl()
            ctrl.set_selected_bones(storage.selected_names)
        except Exception:
            pass

        context.area.tag_redraw()
        return {'FINISHED'}


# ==============================================================================
# SELECT AFFECTED VERTICES
# ==============================================================================

class OBJECT_OT_mw_select_affect_vertices(bpy.types.Operator):
    bl_idname = "object.mw_select_affect_vertices"
    bl_label = "Select Affect Vertices"
    bl_description = (
        "Select all vertices affected in the current context — "
        "bone weight > 0 on the active bone (Deform Bones tab), "
        "or explicit mask override on the active layer (Layers tab)"
    )
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not _is_valid_mesh(obj):
            return {'CANCELLED'}

        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        try:
            ctrl = CoreFacade(context).get_ctrl()
            affected_indices = ctrl.get_affected_vertex_indices()
        except ValueError as e:
            self.report({'WARNING'}, str(e))
            return {'CANCELLED'}

        bm = bmesh.from_edit_mesh(obj.data)
        bm.verts.ensure_lookup_table()

        for v in bm.verts:
            v.select = (v.index in affected_indices)

        bm.select_flush_mode()
        bmesh.update_edit_mesh(obj.data)

        return {'FINISHED'}


# ==============================================================================
# SHOW AFFECTING BONES
# ==============================================================================

class MESH_OT_show_affect_bone(bpy.types.Operator):
    """List bones influencing the current vertex selection; selecting an
    entry from the popup menu activates that vertex group."""

    bl_idname = "mesh.show_affect_bone"
    bl_label = "Show Affecting Bones"
    bl_options = {'REGISTER', 'UNDO'}

    bone_name: bpy.props.StringProperty()

    @classmethod
    def poll(cls, context):
        return (
            context.mode == 'EDIT_MESH'
            and context.active_object
            and context.active_object.type == 'MESH'
        )

    def execute(self, context):
        if self.bone_name:
            obj = context.active_object
            if self.bone_name in obj.vertex_groups:
                vg = obj.vertex_groups[self.bone_name]
                storage = obj.superskin_storage
                clear_all_selected(obj)
                add_vg_selected(obj, self.bone_name)
                storage.selection_history = str(vg.index)
                storage.last_clicked_index = vg.index
                try:
                    ctrl = CoreFacade(context).get_ctrl()
                    ctrl.set_selected_bones(storage.selected_names)
                    ctrl.set_active_bone_name(self.bone_name)
                except Exception:
                    pass
                self.report({'INFO'}, f"Selected Vertex Group: {self.bone_name}")
            else:
                self.report({'WARNING'}, f"ไม่พบ Vertex Group ชื่อ {self.bone_name} ใน Object นี้")
            return {'FINISHED'}

        context.window_manager.popup_menu(self.draw_menu, title="Bones Influencing Selection")
        return {'FINISHED'}

    def draw_menu(self, menu, context):
        layout = menu.layout
        obj = context.active_object

        obj.update_from_editmode()
        selected_v_indices = {v.index for v in obj.data.vertices if v.select}

        influencing_bones = set()

        if selected_v_indices:
            try:
                ctrl = CoreFacade(context).get_ctrl()
                layer_dict = ctrl.get_active_layer_weights_for_display()
            except ValueError:
                layer_dict = {}

            for v_idx in selected_v_indices:
                for bone_name, weight in layer_dict.get(v_idx, {}).items():
                    if weight > 0.001:
                        influencing_bones.add(bone_name)

        if influencing_bones:
            for bone in sorted(influencing_bones):
                props = layout.operator(self.bl_idname, text=bone, icon='GROUP_VERTEX')
                props.bone_name = bone
        else:
            layout.label(text="No influencing bones found or no vertex selected", icon='ERROR')


# ==============================================================================
# POPUP INFLUENCES DIALOG
# ==============================================================================

class OBJECT_OT_mw_popup_affect_influences(bpy.types.Operator):
    bl_idname = "object.mw_popup_affect_influences"
    bl_label = "Affecting Influences"
    bl_description = "Show influences affecting selected vertices"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not _is_valid_mesh(obj):
            self.report({'WARNING'}, "No active mesh")
            return {'CANCELLED'}

        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')

        obj.update_from_editmode()
        selected_verts = [v for v in obj.data.vertices if v.select]

        if not selected_verts:
            self.report({'WARNING'}, "No vertices selected")
            return {'CANCELLED'}

        group_indices = set()
        for v in selected_verts:
            for g in v.groups:
                if g.weight > 0.001:
                    group_indices.add(g.group)

        if not group_indices:
            self.report({'WARNING'}, "Selected vertices have no weights")
            return {'CANCELLED'}

        self._group_names = [
            obj.vertex_groups[i].name
            for i in sorted(group_indices)
            if i < len(obj.vertex_groups)
        ]

        return context.window_manager.invoke_props_dialog(self, width=280)

    def invoke(self, context, event):
        self._group_names = []
        return self.execute(context)

    def draw(self, context):
        layout = self.layout
        layout.label(text="Influences on selection:", icon='BONE_DATA')
        layout.separator()

        if not self._group_names:
            layout.label(text="Nothing found", icon='INFO')
            return

        box = layout.box()
        for name in self._group_names:
            row = box.row(align=True)
            op = row.operator(
                "object.mw_select_specific_vertex_group",
                text=name,
                icon='VERTEX_GROUP'
            )
            op.group_name = name


class OBJECT_OT_mw_select_specific_vertex_group(bpy.types.Operator):
    bl_idname = "object.mw_select_specific_vertex_group"
    bl_label = "Select Vertex Group"
    bl_options = {'INTERNAL'}

    group_name: bpy.props.StringProperty()

    def execute(self, context):
        obj = context.active_object
        if obj and self.group_name in obj.vertex_groups:
            vg = obj.vertex_groups[self.group_name]
            storage = obj.superskin_storage
            clear_all_selected(obj)
            add_vg_selected(obj, self.group_name)
            storage.selection_history = str(vg.index)
            storage.last_clicked_index = vg.index
            try:
                ctrl = CoreFacade(context).get_ctrl()
                ctrl.set_selected_bones(storage.selected_names)
                ctrl.set_active_bone_name(self.group_name)
            except Exception:
                pass
        return {'FINISHED'}


# ==============================================================================
# POPUP INFLUENCES MENU
# ==============================================================================

class MT_mw_popup_affect_influences_menu(bpy.types.Menu):
    bl_label = "Affecting Influences"
    bl_idname = "VIEW3D_MT_superskin_affect_influences"

    def draw(self, context):
        layout = self.layout
        obj = context.active_object

        if not _is_valid_mesh(obj):
            layout.label(text="No active mesh")
            return

        active_index = obj.superskin_storage.last_clicked_index
        if not (0 <= active_index < len(obj.vertex_groups)):
            layout.label(text="No active Vertex Group", icon='WARNING')
            return
        active_vg_name = obj.vertex_groups[active_index].name

        if obj.mode == 'EDIT':
            obj.update_from_editmode()

        target_vertices = []
        selected_verts = [v for v in obj.data.vertices if v.select]

        if selected_verts:
            for v in selected_verts:
                for g in v.groups:
                    if g.group == active_index and g.weight > 0.001:
                        target_vertices.append(v)
                        break
        else:
            for v in obj.data.vertices:
                for g in v.groups:
                    if g.group == active_index and g.weight > 0.001:
                        target_vertices.append(v)
                        break

        if not target_vertices:
            layout.label(text=f"'{active_vg_name}' has no weight on mesh", icon='INFO')
            return

        group_indices = set()
        for v in target_vertices:
            for g in v.groups:
                if g.weight > 0.001 and g.group != active_index:
                    group_indices.add(g.group)

        if not group_indices:
            layout.label(text="100% Clean Weight (No other influences)", icon='CHECKMARK')
            return

        layout.label(text=f"Shared Influences with '{active_vg_name}':", icon='BONE_DATA')
        layout.separator()

        for g_id in sorted(group_indices):
            if g_id < len(obj.vertex_groups):
                g_name = obj.vertex_groups[g_id].name
                prop = layout.operator(
                    "object.mw_select_specific_vertex_group",
                    text=g_name,
                    icon='VERTEX_GROUP'
                )
                prop.group_name = g_name


# ==============================================================================
# SAVE WEIGHT AND EXIT
# ==============================================================================

class SUPERSKIN_OT_save_weight_and_exit(bpy.types.Operator):
    """Bake temporary vertex group weights into custom properties storage and clear temp layers"""
    bl_idname = "superskin.save_weight_and_exit"
    bl_label = "Save Weight and Exit"
    bl_description = "Commit modified temporary weights back into layer custom properties storage"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object

        # Suppress internal transactional updates during the mode bounce.
        was_suppressing = getattr(context.scene, "superskin_internal_transaction", False)
        context.scene.superskin_internal_transaction = True

        try:
            # Force Object Mode to securely commit updates to custom ID data properties.
            if obj.mode == 'EDIT':
                bpy.ops.object.mode_set(mode='OBJECT')

            storage = LayerStorageService(obj.data)
            active_idx = storage.get_active_layer_index()

            # Extract weights and masks from temporary vertex groups.
            layer_dict, mask_dict, _ = read_temp_vgs_to_layer(obj)
            storage.write_layer_dict(active_idx, layer_dict)
            if mask_dict:
                storage.write_mask_dict(active_idx, mask_dict)

            # Delete all temporary vertex groups and properties.
            delete_temp_vgs(obj)

            # Inject an explicit undo step into Blender's history stack to maintain synchronization.
            bpy.ops.ed.undo_push(message="SuperSkinPro: Save Layer Weights")

        finally:
            context.scene.superskin_internal_transaction = was_suppressing

        return {'FINISHED'}


# ==============================================================================
# REGISTRATION
# ==============================================================================

_classes = (
    SUPERSKIN_OT_toggle_vg_lock,
    SUPERSKIN_OT_select_all_vgs,
    OBJECT_OT_mw_select_affect_vertices,
    MESH_OT_show_affect_bone,
    OBJECT_OT_mw_popup_affect_influences,
    OBJECT_OT_mw_select_specific_vertex_group,
    MT_mw_popup_affect_influences_menu,
    SUPERSKIN_OT_save_weight_and_exit,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
