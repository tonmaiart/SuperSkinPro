"""Bone Picker operators — moved from operators/ops_shortcuts.py."""

import bpy
from ...core.facade import CoreFacade
from mathutils import Vector
from bpy_extras import view3d_utils
from . import deform_overlay as _deform_overlay

_bone_picker_active = False


class OBJECT_OT_ssp_toggle_color_bone_style(bpy.types.Operator):
    bl_idname = "superskin.toggle_color_bone_style"
    bl_label = "Toggle Color Bone Style"

    def execute(self, context):
        from ...interface.utils.op_exec import run_domain_via_unified
        return run_domain_via_unified(context, "multi_color_preview", "toggle_multi_color")


class OBJECT_OT_ssp_clear_multi_selection(bpy.types.Operator):
    bl_idname = "superskin.clear_multi_selection"
    bl_label = "Clear Multi Bone Selection"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if not obj:
            return {'CANCELLED'}

        storage = getattr(obj, "superskin_storage", None)
        if storage:
            storage.selected_names = ""
            storage.selection_history = ""
            storage.last_clicked_index = -1

        CoreFacade(context).show_toast("CLEAN ALL MULTI SELECTION", duration=1.0)
        return {'FINISHED'}


class OBJECT_OT_mw_pick_bone(bpy.types.Operator):
    bl_idname = "object.mw_pick_bone"
    bl_label = "Pick Bone (Live Weight Visualize Hybrid)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return False
        if getattr(context.scene, "superskin_is_mask_mode", False):
            return False
        if getattr(context.scene, "superskin_skin_sub_tabs", False):
            return False
        return True

    bone_detect_dist: bpy.props.IntProperty(
        name="Bone Detect Distance (2D)",
        description="ระยะรัศมีรอบเมาส์ในการตรวจจับกระดูกบนหน้าจอ (หน่วยเป็นพิกเซล)",
        default=30, min=5, max=200
    )

    vertex_search_radius: bpy.props.FloatProperty(
        name="Vertex Search Radius",
        description="รัศมีสูงสุดในการควานหา Vertex ใต้เมาส์หลังจาก Raycast โดนผิวเมช",
        default=50.0, min=1.0, max=500.0
    )

    def modal(self, context, event):
        global _bone_picker_active
        context.area.tag_redraw()
        obj = context.active_object

        # ── Mouse move: hover preview + sweep add ────────────────────────
        if event.type == 'MOUSEMOVE':
            self.mouse_x = event.mouse_region_x
            self.mouse_y = event.mouse_region_y

            if self.is_sweep_add:
                self.hovered_bone = self._get_hovered_bone(context, bone_line_only=True)
                _deform_overlay.set_hover(self.hovered_bone)
                for name in self._get_hovered_bones_in_range(context):
                    self._sweep_add_bone(context, name)
            elif self.is_sweep_remove:
                self.hovered_bone = self._get_hovered_bone(context, bone_line_only=True)
                _deform_overlay.set_hover(self.hovered_bone)
                for name in self._get_hovered_bones_in_range(context):
                    self._sweep_remove_bone(context, name)
            else:
                self.hovered_bone = self._get_hovered_bone(context, bone_line_only=self._multi_mode)
                _deform_overlay.set_hover(self.hovered_bone)
                if self.hovered_bone and self.hovered_bone != self._last_hovered:
                    self._last_hovered = self.hovered_bone
                    vg = obj.vertex_groups.get(self.hovered_bone)
                    if vg:
                        ctrl = CoreFacade(context).get_ctrl()
                        ctrl.set_active_bone_name(self.hovered_bone)
                        ctrl.apply_active_bone()
                        self._sync_list_idx(obj, vg.index)

        # ── Left click: sweep add to multi ───────────────────────────────
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            self.is_sweep_add = True
            self._multi_mode = True
            self.hovered_bone = self._get_hovered_bone(context, bone_line_only=True)
            if self.hovered_bone:
                self._sweep_add_bone(context, self.hovered_bone)

        elif event.type == 'LEFTMOUSE' and event.value == 'RELEASE':
            self.is_sweep_add = False

        # ── Right click: cancel, revert to initial bone ──────────────────
        elif event.type == 'RIGHTMOUSE':
            if event.value == 'RELEASE':
                _bone_picker_active = False
                # stop_bone_picker_draw() was a no-op; removed in Phase 8
                _deform_overlay.clear_hover()
                _deform_overlay.set_holding(False)
                self._restore_overlay()
                if obj and self.initial_vg_index != -1:
                    obj.superskin_storage.last_clicked_index = self.initial_vg_index
                return {'CANCELLED'}

        # ── Middle mouse drag: sweep remove from multi-selection ─────────
        elif event.type == 'MIDDLEMOUSE' and event.value == 'PRESS':
            self.is_sweep_remove = True
            self._multi_mode = True
            self.hovered_bone = self._get_hovered_bone(context, bone_line_only=True)
            if self.hovered_bone:
                self._sweep_remove_bone(context, self.hovered_bone)

        elif event.type == 'MIDDLEMOUSE' and event.value == 'RELEASE':
            self.is_sweep_remove = False

        # ── Release 2: single-select only when no multi-selection active ──
        elif event.type == 'TWO' and event.value == 'RELEASE':
            if not self._multi_mode and self.hovered_bone:
                self._select_single_bone(context, self.hovered_bone)
            _bone_picker_active = False
            # stop_bone_picker_draw() was a no-op; removed in Phase 8
            _deform_overlay.clear_hover()
            _deform_overlay.set_holding(False)
            self._restore_overlay()
            return {'FINISHED'}

        # ── ESC: cancel ───────────────────────────────────────────────────
        elif event.type == 'ESC':
            _bone_picker_active = False
            # stop_bone_picker_draw() was a no-op; removed in Phase 8
            _deform_overlay.clear_hover()
            _deform_overlay.set_holding(False)
            self._restore_overlay()
            if obj and self.initial_vg_index != -1:
                obj.superskin_storage.last_clicked_index = self.initial_vg_index
            return {'CANCELLED'}

        elif event.type in {'WHEELUPMOUSE', 'WHEELDOWNMOUSE'}:
            return {'PASS_THROUGH'}

        return {'RUNNING_MODAL'}

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _sync_list_idx(self, obj, vg_index: int):
        """Sync superskin_bones_idx so template_list highlights the selected row."""
        for i, item in enumerate(obj.superskin_bones_collection):
            if not item.is_orphan and item.vg_index == vg_index:
                obj.superskin_bones_idx = i
                return

    def _select_single_bone(self, context, bone_name):
        """Release 2: clear multi, make bone_name the only selected bone."""
        obj = context.active_object
        storage = getattr(obj, "superskin_storage", None)
        if not storage:
            return
        self.session_pool.clear()
        self.session_recent_bone = None

        vg = obj.vertex_groups.get(bone_name)
        if not vg:
            return

        # Use the comma-bounded format the BoneListAdapter expects so the
        # list row highlights correctly.
        storage.selected_names   = f",{bone_name},"
        storage.last_clicked_index = vg.index
        storage.selection_history  = str(vg.index)
        self.session_recent_bone   = bone_name
        self._sync_list_idx(obj, vg.index)

        # Sync layer meta — same two calls the row-click operator makes via
        # on_single_select so the active bone is persisted per-layer.
        try:
            ctrl = CoreFacade(context).get_ctrl()
            ctrl.set_selected_bones(storage.selected_names)
            ctrl.set_active_bone_name(bone_name)
        except Exception:
            pass

    def _sweep_add_bone(self, context, bone_name):
        """Alt+Middle sweep: add bone_name to multi-selection pool."""
        obj = context.active_object
        storage = getattr(obj, "superskin_storage", None)
        if not storage:
            return
        if f",{bone_name}," in storage.selected_names:
            return
        if not storage.selected_names:
            storage.selected_names = ","
        from ...core.facade import CoreFacade
        CoreFacade(context).add_vg_selected(obj, bone_name)
        vg = obj.vertex_groups.get(bone_name)
        if vg:
            storage.last_clicked_index = vg.index
            storage.selection_history = str(vg.index)
            self.session_recent_bone = bone_name
            self.session_pool.add(bone_name)
            self._sync_list_idx(obj, vg.index)

    def _sweep_remove_bone(self, context, bone_name):
        """Alt+Right sweep: remove bone_name from multi-selection pool."""
        obj = context.active_object
        storage = getattr(obj, "superskin_storage", None)
        if not storage:
            return
        if f",{bone_name}," not in storage.selected_names:
            return
        from ...core.facade import CoreFacade
        if CoreFacade(context).remove_vg_selected(obj, bone_name):
            self.session_pool.discard(bone_name)
            remaining = [n for n in storage.selected_names.split(",") if n]
            if remaining:
                last = remaining[-1]
                vg = obj.vertex_groups.get(last)
                if vg:
                    storage.last_clicked_index = vg.index
                    storage.selection_history = str(vg.index)
                    self.session_recent_bone = last
            else:
                self.session_recent_bone = None

    # ── Detection helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _seg_dist_2d(p, a, b):
        """Perpendicular distance from 2D point p to segment a-b."""
        ab = b - a
        denom = ab.dot(ab)
        if denom < 1e-10:
            return (p - a).length
        t = max(0.0, min(1.0, (p - a).dot(ab) / denom))
        return (p - (a + t * ab)).length

    def _iter_nearby_bones(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return
        armature = self._get_armature(obj)
        if not armature:
            return
        region = context.region
        rv3d = context.region_data
        mouse_vec = Vector((self.mouse_x, self.mouse_y))
        vg_names = {vg.name for vg in obj.vertex_groups}
        deform_bones = {b.name for b in armature.data.bones if b.use_deform}
        for bone in armature.pose.bones:
            if bone.name not in deform_bones or bone.name not in vg_names:
                continue
            head_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, armature.matrix_world @ bone.head)
            tail_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, armature.matrix_world @ bone.tail)
            if head_2d is None or tail_2d is None:
                continue
            dist = self._seg_dist_2d(mouse_vec, head_2d, tail_2d)
            if dist < self.bone_detect_dist:
                yield bone.name, dist

    def _get_hovered_bones_in_range(self, context):
        return [name for name, _ in self._iter_nearby_bones(context)]

    def _get_hovered_bone(self, context, bone_line_only=False):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return None
        armature = self._get_armature(obj)
        if not armature:
            return None

        if bone_line_only:
            nearby = list(self._iter_nearby_bones(context))
            return min(nearby, key=lambda t: t[1])[0] if nearby else None

        region = context.region
        rv3d = context.region_data
        mouse_vec = Vector((self.mouse_x, self.mouse_y))
        vg_names = {vg.name for vg in obj.vertex_groups}
        deform_bones = {b.name for b in armature.data.bones if b.use_deform}

        closest_bone = None
        closest_dist = float('inf')

        for bone in armature.pose.bones:
            if bone.name not in deform_bones or bone.name not in vg_names:
                continue
            head_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, armature.matrix_world @ bone.head)
            tail_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, armature.matrix_world @ bone.tail)
            if head_2d is None or tail_2d is None:
                continue
            dist = self._seg_dist_2d(mouse_vec, head_2d, tail_2d)
            if dist < closest_dist and dist < self.bone_detect_dist:
                closest_dist = dist
                closest_bone = bone.name

        if closest_bone:
            return closest_bone

        ray_origin = view3d_utils.region_2d_to_origin_3d(region, rv3d, mouse_vec)
        ray_dir    = view3d_utils.region_2d_to_vector_3d(region, rv3d, mouse_vec)
        depsgraph  = context.evaluated_depsgraph_get()
        hit, loc, norm, idx, hit_obj, matrix = context.scene.ray_cast(depsgraph, ray_origin, ray_dir)

        # hit_obj is the evaluated object; compare via .original to match the base object
        if hit and hit_obj is not None and hit_obj.original is obj:
            # Use original mesh for vertex group data (evaluated mesh may lack .groups)
            mesh = obj.data
            poly = mesh.polygons[idx]
            closest_v = None
            closest_v_dist = float('inf')
            for v_idx in poly.vertices:
                v = mesh.vertices[v_idx]
                v_world = obj.matrix_world @ v.co
                v_2d = view3d_utils.location_3d_to_region_2d(region, rv3d, v_world)
                if v_2d:
                    d = (v_2d - mouse_vec).length
                    if d < closest_v_dist and d < self.vertex_search_radius:
                        closest_v_dist = d
                        closest_v = v
            if closest_v and closest_v.groups:
                max_w = -1.0
                best = None
                for g in closest_v.groups:
                    if g.group < len(obj.vertex_groups):
                        g_name = obj.vertex_groups[g.group].name
                        if g_name in deform_bones and g_name in vg_names and g.weight > max_w:
                            max_w = g.weight
                            best = g_name
                return best

        return None

    def _get_armature(self, obj):
        for mod in obj.modifiers:
            if mod.type == 'ARMATURE':
                return mod.object
        return None

    def _restore_overlay(self):
        """Restore overlay visibility to state before picker was invoked."""
        if not self._overlay_was_visible:
            _deform_overlay.hide()

    def invoke(self, context, event):
        obj = context.active_object
        self._saved_layer = 0
        try:
            self._saved_layer = CoreFacade(context).get_active_layer_index()
        except Exception:
            pass

        if not obj:
            return {'CANCELLED'}

        self.mouse_x = event.mouse_region_x
        self.mouse_y = event.mouse_region_y
        self.hovered_bone = None
        self.initial_vg_index = obj.superskin_storage.last_clicked_index if obj else -1
        self.is_sweep_add = False
        self.is_sweep_remove = False
        self._multi_mode = False
        self._last_hovered = None

        storage = getattr(obj, "superskin_storage", None)
        if storage and storage.selected_names:
            self.session_pool = set(n for n in storage.selected_names.split(",") if n)
        else:
            self.session_pool = set()

        self.session_recent_bone = None
        if storage and 0 <= storage.last_clicked_index < len(obj.vertex_groups):
            self.session_recent_bone = obj.vertex_groups[storage.last_clicked_index].name

        self._overlay_was_visible = _deform_overlay.is_visible()
        _deform_overlay.show()
        _deform_overlay.set_holding(True)
        context.area.tag_redraw()
        # start_bone_picker_draw() was a no-op; removed in Phase 8
        global _bone_picker_active
        _bone_picker_active = True
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


class SUPERSKIN_OT_toggle_deform_bone_overlay(bpy.types.Operator):
    bl_idname = "superskin.toggle_deform_bone_overlay"
    bl_label = "Toggle Deform Bone Overlay"
    bl_description = "Show or hide a persistent overlay of all deform bones in Edit Mode"
    bl_options = {'REGISTER'}

    def execute(self, context):
        _deform_overlay.toggle()
        return {'FINISHED'}


_DRAG_THRESHOLD = 4  # pixels before a right-click becomes a drag


class SUPERSKIN_OT_adjust_bone_overlay_size(bpy.types.Operator):
    """Alt+RMB drag to resize bone overlay."""
    bl_idname = "superskin.adjust_bone_overlay_size"
    bl_label = "Adjust Bone Overlay Size"
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return not _bone_picker_active

    def modal(self, context, event):
        if event.type == 'MOUSEMOVE':
            delta = event.mouse_x - self._initial_x
            if not self._is_dragging and abs(delta) > _DRAG_THRESHOLD:
                self._is_dragging = True
            if self._is_dragging and delta != 0:
                bp = context.window_manager.superskin_bone_picker_prefs
                new_size = max(0.1, min(5.0, bp.overall_size + delta * 0.01))
                bp.overall_size = new_size
                context.area.header_text_set(f"Bone Overlay Size: {new_size:.2f}")
                _deform_overlay._tag_redraw()
                context.window.cursor_warp(self._initial_x, self._initial_y)

        elif event.type == 'RIGHTMOUSE' and event.value == 'RELEASE':
            context.window.cursor_modal_restore()
            context.area.header_text_set(None)
            return {'FINISHED'}

        elif event.type == 'ESC':
            context.window.cursor_modal_restore()
            context.area.header_text_set(None)
            if self._is_dragging:
                context.window_manager.superskin_bone_picker_prefs.overall_size = self._backup_size
                _deform_overlay._tag_redraw()
            return {'CANCELLED'}

        return {'RUNNING_MODAL'}

    def invoke(self, context, event):
        if _bone_picker_active:
            return {'CANCELLED'}
        if not context.space_data or context.space_data.type != 'VIEW_3D':
            return {'CANCELLED'}
        self._initial_x = event.mouse_x
        self._initial_y = event.mouse_y
        try:
            self._backup_size = context.window_manager.superskin_bone_picker_prefs.overall_size
        except Exception:
            self._backup_size = 1.0
        self._is_dragging = False
        context.window.cursor_modal_set('NONE')
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


_classes = (
    OBJECT_OT_ssp_toggle_color_bone_style,
    OBJECT_OT_ssp_clear_multi_selection,
    OBJECT_OT_mw_pick_bone,
    SUPERSKIN_OT_toggle_deform_bone_overlay,
    SUPERSKIN_OT_adjust_bone_overlay_size,
)


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
