"""Deform Bone List UIList, row-click operator, adapter, and draw function.

Moved from ui/widget_deform_bones.py as part of the SKINNING tab domain
extraction. All imports that previously pointed at ui/list_widget/ now
point at the canonical shared/list_widget/ package.
"""

import bpy
import traceback

from ...shared.list_widget import (
    SuperSkinListMixin,
    register_adapter,
    draw_list_with_sidebar,
)
from ...shared.list_widget.select_ops import (
    ListSelectionAdapter,
    get_adapter,
    resolve_row_click_selection,
)
from ...ui.utils import _get_visible_influence_bones


# ==============================================================================
# Shared hook bodies — plain functions, no bpy.types.UIList dependency.
# Used by both MESH_UL_influence_list_view (the real UIList) and
# _BoneListVisibilityHooks (a plain-Python twin used outside the draw cycle).
# ==============================================================================

def _extra_keep_predicate_impl(context, data, item, original_idx):
    """Draw-time row filter for the unified (real + orphan) mirror list."""
    adv = context.scene.superskin_adv_settings
    mode = adv.bone_list_filter_mode

    if getattr(item, 'is_orphan', False):
        return True

    if mode == 'ORPHAN':
        return False
    elif mode == 'INFLUENCE':
        influenced_bones = _get_visible_influence_bones(context, data)
        return item.name in influenced_bones
    return True


# ==============================================================================
# Plain-Python visibility hooks twin
# ==============================================================================

class _BoneListVisibilityHooks(SuperSkinListMixin):
    """Plain-Python twin of MESH_UL_influence_list_view's hooks, used only
    by BoneListAdapter.get_keys_in_visual_order() for off-draw-cycle
    visibility computation. Orphan rows are excluded here (unlike the real
    UIList's own predicate), since they must never enter a range-select span
    between two real bone rows."""

    def get_item_key(self, item):
        return item.name

    def get_display_order(self, context, data):
        items = getattr(data, 'superskin_bones_collection', ())
        return list(range(len(items)))

    def extra_keep_predicate(self, context, data, item, original_idx):
        if getattr(item, 'is_orphan', False):
            return False
        return _extra_keep_predicate_impl(context, data, item, original_idx)


_bone_visibility_hooks = _BoneListVisibilityHooks()


# ==============================================================================
# Adapter
# ==============================================================================

class BoneListAdapter(ListSelectionAdapter):
    """Bridge between the generic row-click operator and the bone-list
    selection storage (``obj.superskin_storage.selected_names`` etc.)."""

    def get_keys_in_visual_order(self, context, obj):
        return _bone_visibility_hooks.compute_visible_keys(
            context, obj, "superskin_bones_collection"
        )

    def read_selection(self, context, obj):
        storage = obj.superskin_storage
        vg_list = obj.vertex_groups

        raw = storage.selected_names
        if not raw or not raw.startswith(","):
            selected_keys = set()
        else:
            selected_keys = {n for n in raw.split(",") if n}

        last_key = None
        if 0 <= storage.last_clicked_index < len(vg_list):
            last_key = vg_list[storage.last_clicked_index].name

        hist = []
        raw_hist = storage.selection_history
        if raw_hist:
            for part in raw_hist.split(","):
                part = part.strip()
                if part:
                    try:
                        idx = int(part)
                        if 0 <= idx < len(vg_list):
                            hist.append(vg_list[idx].name)
                    except ValueError:
                        pass

        return selected_keys, last_key, hist

    def write_selection(self, context, obj, selected_keys, last_key, history):
        storage = obj.superskin_storage
        vg_list = obj.vertex_groups
        name_to_idx = {vg.name: i for i, vg in enumerate(vg_list)}

        if selected_keys:
            storage.selected_names = (
                "," + ",".join(sorted(selected_keys, key=lambda n: name_to_idx.get(n, 9999))) + ","
            )
        else:
            storage.selected_names = ","

        if last_key and last_key in name_to_idx:
            storage.last_clicked_index = name_to_idx[last_key]
        else:
            storage.last_clicked_index = -1

        hist_indices = []
        for k in history:
            idx = name_to_idx.get(k)
            if idx is not None:
                hist_indices.append(str(idx))
        storage.selection_history = ",".join(hist_indices)

    def on_single_select(self, context, obj, key):
        """Reproduce the tail of the now-removed bone row-click operator.

        Clears ``active_orphan_name``, exits mask mode, persists selection
        to the active layer via CoreFacade, and sets the active bone name.
        """
        obj.superskin_storage.active_orphan_name = ""

        from ...ui.utils import exit_mask_mode_if_active
        exit_mask_mode_if_active(context, obj)

        try:
            from ...core.facade import CoreFacade
            ctrl = CoreFacade(context).get_ctrl()
            ctrl.set_selected_bones(obj.superskin_storage.selected_names)
            storage = obj.superskin_storage
            vg_list = obj.vertex_groups
            if 0 <= storage.last_clicked_index < len(vg_list):
                ctrl.set_active_bone_name(vg_list[storage.last_clicked_index].name)
            try:
                ctrl.apply_active_bone()
            except Exception:
                pass
        except Exception:
            traceback.print_exc()


# ==============================================================================
# Bone Row-Click Operator
# ==============================================================================

class SUPERSKIN_OT_select_vertex_group_row(bpy.types.Operator):
    """Select a vertex-group row in the Deform Bones list.

    Supports Ctrl-click (toggle), Shift-click (range-select), and
    Alt+Shift-click (select all visible). Dedicated bl_idname — NOT shared
    with the Layers tab operator.
    """

    bl_idname = "superskin.select_vertex_group_row"
    bl_label = "Select Vertex Group Row"
    bl_options = {'INTERNAL'}

    index: bpy.props.IntProperty(name="Vertex Group Index")

    def invoke(self, context, event):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}

        vg_list = obj.vertex_groups
        if self.index < 0 or self.index >= len(vg_list):
            return {'CANCELLED'}

        item_key = vg_list[self.index].name

        was_suppressing = context.scene.superskin_internal_transaction
        context.scene.superskin_internal_transaction = True
        try:
            adapter = get_adapter('BONES')
            selected_keys, last_key, history = adapter.read_selection(context, obj)
            visual_order = adapter.get_keys_in_visual_order(context, obj)

            selected_keys, last_key, history = resolve_row_click_selection(
                selected_keys, last_key, history, item_key, visual_order, event
            )

            adapter.write_selection(context, obj, selected_keys, last_key, history)
            adapter.on_single_select(context, obj, item_key)

        finally:
            context.scene.superskin_internal_transaction = was_suppressing

        _sync_bones_idx_to_real_bone(obj, vg_index=self.index)
        context.area.tag_redraw()
        return {'FINISHED'}


def _sync_bones_idx_to_real_bone(obj, vg_index: int):
    """Point ``obj.superskin_bones_idx`` at the real-bone row that was just
    clicked. Drives only the blue row-highlight in the UIList."""
    for i, item in enumerate(obj.superskin_bones_collection):
        if not item.is_orphan and item.vg_index == vg_index:
            obj.superskin_bones_idx = i
            return


# ==============================================================================
# UIList: Influence List View
# ==============================================================================

class MESH_UL_influence_list_view(SuperSkinListMixin, bpy.types.UIList):

    def domain(self) -> str:
        return 'BONES'

    def get_item_key(self, item) -> str:
        return item.name

    def get_display_order(self, context, data):
        items = getattr(data, 'superskin_bones_collection', ())
        return list(range(len(items)))

    def is_selected(self, context, data, key: str) -> bool:
        return f",{key}," in data.superskin_storage.selected_names

    def draw_main_icon(self, context, data, item) -> str:
        if item.is_orphan:
            return 'ERROR'
        influenced_set = _get_visible_influence_bones(context, data)
        return 'BONE_DATA' if item.name in influenced_set else 'BLANK1'

    def get_row_operator_id(self, item=None) -> str:
        if item is not None and item.is_orphan:
            return "superskin.select_orphan_bone_row"
        return "superskin.select_vertex_group_row"

    def set_row_operator_props(self, op, item):
        if item.is_orphan:
            op.orphan_name = item.name
        else:
            op.index = item.vg_index

    def _ensure_filter_dependencies(self, context, data):
        adv = context.scene.superskin_adv_settings
        _ = adv.bone_list_filter_mode

    def extra_keep_predicate(self, context, data, item, original_idx: int) -> bool:
        return _extra_keep_predicate_impl(context, data, item, original_idx)

    def draw_extra_icon(self, context, layout, data, item, index: int):
        lock_icon = 'LOCKED' if item.lock_weight else 'UNLOCKED'
        op_lock = layout.operator(
            "superskin.toggle_vg_lock", text="", icon=lock_icon, emboss=False,
        )
        op_lock.index = item.vg_index
        op_lock.vg_name = item.name


# ==============================================================================
# Overflow menu
# ==============================================================================

class SUPERSKIN_MT_bone_extra_overflow(bpy.types.Menu):
    """Overflow menu for secondary bone-list actions: bone utilities
    (Show Affect Bone, Auto Assign) plus clipboard (Copy/Cut/Paste)."""
    bl_label = "More"
    bl_idname = "SUPERSKIN_MT_bone_extra_overflow"

    def draw(self, context):
        layout = self.layout
        layout.operator("mesh.show_affect_bone",
                        text="Show Affect Bone", icon='BONE_DATA')


# ==============================================================================
# Draw function (called by prefs.py draw_section_fn)
# ==============================================================================

def draw_influence_list_system(layout, context, rows=8):
    """Draw the Deform Bones list with search box and side buttons."""
    obj = context.active_object
    if not obj or obj.type != 'MESH' or not hasattr(obj, "superskin_storage"):
        return

    adv = context.scene.superskin_adv_settings
    scene = context.scene

    draw_list_with_sidebar(
        layout, context,
        ui_list_idname="MESH_UL_influence_list_view",
        data=obj,
        collection_prop="superskin_bones_collection",
        active_data=obj,
        active_prop="superskin_bones_idx",
        search_owner=obj.superskin_storage,
        search_prop="filter_name",
        rows=rows,
        button_defs=[
            ("toggle", scene, "superskin_skin_sub_tabs", 'MOD_MASK'),
            ("separator", 1.0),
            ("enum_radio", adv, "bone_list_filter_mode", 'NONE', 'LONGDISPLAY'),
            ("enum_radio", adv, "bone_list_filter_mode", 'INFLUENCE', 'BONE_DATA'),
            ("enum_radio", adv, "bone_list_filter_mode", 'ORPHAN', 'ERROR'),
            ("separator", 1.0),
            ("operator", "object.mw_select_affect_vertices",
             'OUTLINER_DATA_POINTCLOUD', "", {}),
            ("separator", 1.0),
            ("menu", "SUPERSKIN_MT_bone_extra_overflow",
             'COLLAPSEMENU', ""),
            ("separator", 2.2),
        ],
    )


# ==============================================================================
# Registration
# ==============================================================================

def register():
    register_adapter('BONES', BoneListAdapter())
    bpy.utils.register_class(SUPERSKIN_OT_select_vertex_group_row)
    bpy.utils.register_class(MESH_UL_influence_list_view)
    bpy.utils.register_class(SUPERSKIN_MT_bone_extra_overflow)


def unregister():
    bpy.utils.unregister_class(SUPERSKIN_MT_bone_extra_overflow)
    bpy.utils.unregister_class(MESH_UL_influence_list_view)
    bpy.utils.unregister_class(SUPERSKIN_OT_select_vertex_group_row)
