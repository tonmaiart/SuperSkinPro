"""ClipboardFeature — Unified Component Architecture implementation for the clipboard domain.

Collapses the old ClipboardDomain (action dispatch) and prefs.py (PropertyGroup,
draw, persistence) into a single UnifiedFeatureExtension subclass.

Owns:
  - SSPrefClipboard PropertyGroup (registered on WindowManager)
  - Action dispatch: copy, cut, paste_add, paste_subtract, paste_replace, select_affected
  - UI layout: draw_section()
  - JSON persistence: populate() / serialize_into()
"""

import bpy
import os

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade


# ==============================================================================
# Property Groups
# ==============================================================================

class SSPrefClipboard(bpy.types.PropertyGroup):
    """Clipboard settings — data type, paste operation, and copy/cut toggle."""
    target_data_type: bpy.props.EnumProperty(
        name="Data Type",
        items=[
            ('BONE', "Bone Deform", "Operate directly on Bone weights"),
            ('LAYER', "Layer Mask", "Operate on Layer mask values"),
        ],
        default='BONE',
    )

    paste_operation: bpy.props.EnumProperty(
        name="Operation",
        items=[
            ('REPLACE', "Replace", "Overwrite destination entirely"),
            ('ADD', "Add", "Merge values up to a ceiling of 1.0"),
            ('SUBTRACT', "Subtract", "Deduct values flooring at 0.0"),
        ],
        default='REPLACE',
    )

    copy_cut_toggle: bpy.props.EnumProperty(
        name="Action",
        items=[
            ('COPY', "Copy", "Capture snapshot into memory"),
            ('CUT', "Cut", "Capture snapshot then wipe source data"),
        ],
        default='COPY',
    )


# ==============================================================================
# ClipboardFeature — UnifiedFeatureExtension
# ==============================================================================

class ClipboardFeature(UnifiedFeatureExtension):
    """Unified extension for the Clipboard domain."""

    # ── Configuration (class attributes) ───────────────────────────────────

    domain_id = "clipboard"
    actions = ["copy", "cut", "paste_add", "paste_subtract", "paste_replace",
               "select_affected"]
    section_title = "Clipboard Manager"
    draw_tab = "SKINNING"
    defaults_path = os.path.join(os.path.dirname(__file__), "default_config.json")

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        from .logic import copy, cut, paste, select_affected
        try:
            if action == "copy":
                copy(core_facade)
            elif action == "cut":
                cut(core_facade)
            elif action == "paste_add":
                paste(core_facade, mode='ADD')
            elif action == "paste_subtract":
                paste(core_facade, mode='SUBTRACT')
            elif action == "paste_replace":
                paste(core_facade, mode='REPLACE')
            elif action == "select_affected":
                return {"status": "FINISHED", "data": select_affected(core_facade)}
            else:
                return {"status": "CANCELLED", "message": f"Unknown action: {action}"}
        except ValueError as e:
            return {"status": "CANCELLED", "message": str(e)}
        return {"status": "FINISHED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Draw the full Clipboard section: data type, copy/cut, paste controls."""
        layout.use_property_decorate = False
        prefs = context.window_manager.superskin_clipboard_prefs

        # ── SECTION: DATA
        box_data = layout.box()
        box_data.label(text="Data", icon='FOLDER_REDIRECT')

        row_data1 = box_data.row(align=True)
        row_data1.prop(prefs, "target_data_type", text="Pick Data")

        row_data2 = box_data.row(align=True)
        row_data2.prop(prefs, "copy_cut_toggle", expand=True)
        op_copy = row_data2.operator("object.ssp_clipboard_data_copy", text="Execute Action")
        op_copy.action_type = prefs.copy_cut_toggle

        row_data3 = box_data.row(align=True)
        row_data3.prop(prefs, "paste_operation", text="Pick Data")

        row_data4 = box_data.row(align=True)
        op_paste = row_data4.operator("object.ssp_clipboard_data_paste", text="Replace | Add | Subtract")

        layout.separator(factor=0.5)

        row_label = layout.row()
        row_label.label(text="Copy and Paste", icon='PASTEFLIPDOWN')

        # ── SECTION: VERTEX
        box_vert = layout.box()
        box_vert.label(text="Vertex", icon='VERTEXSEL')

        row_vert = box_vert.row(align=True)
        row_vert.scale_y = 1.1
        row_vert.operator("object.ssp_copy_weight", text="Copy Weight", icon='COPYDOWN')
        row_vert.operator("object.ssp_paste_weight_replace", text="Paste Weight (Replace)", icon='PASTEDOWN')

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """No persistent preferences for the clipboard domain."""
        pass

    def serialize_into(self, full_dict: dict) -> None:
        """No persistent preferences for the clipboard domain."""
        pass


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register PropertyGroups on WindowManager and the extension with UnifiedRegistry."""
    bpy.utils.register_class(SSPrefClipboard)
    bpy.types.WindowManager.superskin_clipboard_prefs = bpy.props.PointerProperty(
        type=SSPrefClipboard, options={'SKIP_SAVE'},
    )
    UnifiedRegistry.register(ClipboardFeature())


def unregister():
    """Unregister PropertyGroups and the extension."""
    UnifiedRegistry.unregister("clipboard")
    try:
        del bpy.types.WindowManager.superskin_clipboard_prefs
    except Exception:
        pass
    bpy.utils.unregister_class(SSPrefClipboard)
