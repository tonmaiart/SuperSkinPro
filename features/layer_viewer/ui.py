"""Layer List UIList, row-click operator, adapter, and draw function.

Moved from ui/widget_tools.py as part of the LAYER tab domain extraction.
All imports that previously pointed at ui/list_widget/ now point at the
canonical shared/list_widget/ package.
"""

import bpy

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
from ...ui.utils import (
    exit_mask_mode_if_active,
    _enforce_visualizer_from_tab_state,
    sync_layers_to_ui_collection,
)


# ==============================================================================
# Plain-Python visibility hooks twin
# ==============================================================================

class _LayerListVisibilityHooks(SuperSkinListMixin):
    """Plain-Python twin of SUPERSKIN_UL_layer_list_view's hooks.
    Used only by LayerListAdapter.get_keys_in_visual_order() for
    off-draw-cycle visibility computation."""

    def get_item_key(self, item):
        return str(item.index)

    def get_display_order(self, context, data):
        return list(range(len(data.superskin_layers_collection)))

    def extra_keep_predicate(self, context, data, item, original_idx):
        return True


_layer_visibility_hooks = _LayerListVisibilityHooks()


# ==============================================================================
# Layer List Adapter
# ==============================================================================

class LayerListAdapter(ListSelectionAdapter):
    """Selection adapter for the LAYERS domain.

    Storage fields:
      ``obj.superskin_storage.layer_selected_indices`` — comma-bounded
        string of selected layer slot indices (e.g. ``",2,4,"``).
      ``obj.superskin_storage.layer_selection_history`` — comma-separated
        slot indices in click order.
    """

    def get_keys_in_visual_order(self, context, obj):
        return _layer_visibility_hooks.compute_visible_keys(
            context, obj, "superskin_layers_collection"
        )

    def read_selection(self, context, obj):
        storage = obj.superskin_storage

        raw = storage.layer_selected_indices
        if not raw or not raw.startswith(","):
            selected_keys = set()
        else:
            selected_keys = {k for k in raw.split(",") if k}

        hist = []
        raw_hist = storage.layer_selection_history
        if raw_hist:
            hist = [k for k in raw_hist.split(",") if k]

        last_key = hist[-1] if hist else None
        return selected_keys, last_key, hist

    def write_selection(self, context, obj, selected_keys, last_key, history):
        storage = obj.superskin_storage

        if selected_keys:
            storage.layer_selected_indices = (
                "," + ",".join(sorted(selected_keys, key=int)) + ","
            )
        else:
            storage.layer_selected_indices = ""

        storage.layer_selection_history = ",".join(history)

    def on_single_select(self, context, obj, key):
        """Switch the active layer to *key* and apply every layer-switch side
        effect. Called once per click by the row operator."""
        obj_mesh_ok = obj and obj.type == 'MESH' and "ss_layers_meta" in obj.data
        if not obj_mesh_ok:
            return
        layer_index = int(key)

        from ...core.facade import CoreFacade
        ctrl = CoreFacade(context).get_ctrl()

        context.scene.superskin_internal_transaction = True
        try:
            exit_mask_mode_if_active(context, obj)
            ctrl.switch_to_layer(layer_index)
            _enforce_visualizer_from_tab_state(context)
            sync_layers_to_ui_collection(obj)
            for window in context.window_manager.windows:
                for area in window.screen.areas:
                    area.tag_redraw()
        finally:
            context.scene.superskin_internal_transaction = False


# ==============================================================================
# Layer Row-Click Operator
# ==============================================================================

# Module-level re-entrance guard (see docs/bug-history/0008 and the
# equivalent guard in the original widget_tools.py).
_layer_select_busy = False


class SUPERSKIN_OT_layer_select_by_item(bpy.types.Operator):
    """Select (and optionally multi-select) a layer row in the Layers list.

    Supports Ctrl-click (toggle), Shift-click (range-select), and
    Alt+Shift-click (select all visible). Dedicated bl_idname — NOT shared
    with the Bones tab operator (cross-domain operator-identity bleed).
    """

    bl_idname = "superskin.layer_select_by_item"
    bl_label = "Select Layer from List"
    bl_options = {'INTERNAL', 'UNDO'}
    layer_index: bpy.props.IntProperty(name="Layer Slot Index")

    def invoke(self, context, event):
        global _layer_select_busy
        if _layer_select_busy:
            return {'CANCELLED'}
        obj = context.active_object
        if not obj or obj.type != 'MESH' or "ss_layers_meta" not in obj.data:
            return {'CANCELLED'}

        item_key = str(self.layer_index)
        _layer_select_busy = True
        was_suppressing = context.scene.superskin_internal_transaction
        try:
            adapter = get_adapter('LAYERS')
            selected_keys, last_key, history = adapter.read_selection(context, obj)
            visual_order = adapter.get_keys_in_visual_order(context, obj)
            selected_keys, last_key, history = resolve_row_click_selection(
                selected_keys, last_key, history, item_key, visual_order, event
            )
            adapter.write_selection(context, obj, selected_keys, last_key, history)
            adapter.on_single_select(context, obj, last_key)
        finally:
            context.scene.superskin_internal_transaction = was_suppressing
            _layer_select_busy = False

        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


# ==============================================================================
# Layer List UIList
# ==============================================================================

class SUPERSKIN_UL_layer_list_view(SuperSkinListMixin, bpy.types.UIList):

    def domain(self) -> str:
        return 'LAYERS'

    def get_item_key(self, item) -> str:
        return str(item.index)

    def get_display_order(self, context, data):
        items = getattr(data, 'superskin_layers_collection', ())
        return list(range(len(items)))

    def is_selected(self, context, data, key: str) -> bool:
        return f",{key}," in data.superskin_storage.layer_selected_indices

    def draw_main_icon(self, context, data, item) -> str:
        return 'NONE'

    def get_row_operator_id(self, item=None) -> str:
        return "superskin.layer_select_by_item"

    def set_row_operator_props(self, op, item):
        op.layer_index = item.index

    def get_filter_query(self, context, data) -> str:
        storage = getattr(data, 'superskin_storage', None)
        if storage is not None:
            return getattr(storage, 'layer_filter_name', '')
        return ''

    def draw_extra_icon(self, context, layout, data, item, index: int):
        eye_icon = 'HIDE_OFF' if item.visible else 'HIDE_ON'
        op_eye = layout.operator(
            "superskin.layer_toggle_visible_by_item",
            text="", icon=eye_icon, emboss=False,
        )
        op_eye.layer_index = item.index


# ==============================================================================
# Overflow menu
# ==============================================================================

class SUPERSKIN_MT_layer_rename_overflow(bpy.types.Menu):
    """Overflow menu for secondary layer-list actions (rename, merge,
    clipboard). bl_idname is unchanged — referenced by string from button_defs
    and must not be renamed per AGENTS.md."""
    bl_label = "More"
    bl_idname = "SUPERSKIN_MT_layer_rename_overflow"

    def draw(self, context):
        layout = self.layout
        layout.operator("superskin.layer_rename_active",
                        text="Rename Layer", icon='OUTLINER_DATA_FONT')
        layout.separator()
        layout.operator("superskin.layer_merge_selected",
                        text="Merge Selected Layers", icon='AUTOMERGE_ON')


# ==============================================================================
# Draw function (called by prefs.py draw_section_fn)
# ==============================================================================

def draw_layer_list(layout, context, rows=8):
    """Draw the layer list with a search box and side buttons."""
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return

    
    draw_list_with_sidebar(
        layout, context,
        ui_list_idname="SUPERSKIN_UL_layer_list_view",
        data=obj,
        collection_prop="superskin_layers_collection",
        active_data=obj,
        active_prop="superskin_layers_idx",
        search_owner=obj.superskin_storage,
        search_prop="layer_filter_name",
        rows=rows,
        button_defs=[
            ("operator", "superskin.layer_add",    'ADD',  "", {}),
            ("operator", "superskin.layer_remove", 'X',    "", {}),
            ("separator", 1.0),
            ("operator", "superskin.layer_move", 'TRIA_UP',   "",
             {"direction": -1}),
            ("operator", "superskin.layer_move", 'TRIA_DOWN', "",
             {"direction":  1}),
            ("separator", 1.0),
            ("menu", "SUPERSKIN_MT_layer_rename_overflow",
             'COLLAPSEMENU', ""),
        ],
    )


# ==============================================================================
# Registration
# ==============================================================================

def register():
    register_adapter('LAYERS', LayerListAdapter())
    bpy.utils.register_class(SUPERSKIN_OT_layer_select_by_item)
    bpy.utils.register_class(SUPERSKIN_UL_layer_list_view)
    bpy.utils.register_class(SUPERSKIN_MT_layer_rename_overflow)


def unregister():
    bpy.utils.unregister_class(SUPERSKIN_MT_layer_rename_overflow)
    bpy.utils.unregister_class(SUPERSKIN_UL_layer_list_view)
    bpy.utils.unregister_class(SUPERSKIN_OT_layer_select_by_item)
