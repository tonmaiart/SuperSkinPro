"""DataIOFeature — Unified Component Architecture implementation for the data_io domain.

Collapses the old WeightIODomain (action dispatch) and prefs.py (PropertyGroup,
draw, persistence) into a single UnifiedFeatureExtension subclass.

Owns:
  - SSPrefWeightIO PropertyGroup (registered on WindowManager)
  - Action dispatch: export_weight, import_weight
  - UI layout: draw_section()
  - JSON persistence: populate() / serialize_into()
"""

import bpy
import os

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


# ==============================================================================
# Property Groups
# ==============================================================================

class SSPrefWeightIO(bpy.types.PropertyGroup):
    """Weight I/O settings (per-machine)."""
    export_precision: bpy.props.IntProperty(
        name="Export Precision",
        description="Number of decimal places for exported weights",
        default=5, min=1, max=9,
    )
    clear_unmapped_bones: bpy.props.BoolProperty(
        name="Clear Unmapped Bones",
        description="Clear target vertex groups if they are not in the JSON file during import",
        default=False,
    )


# ==============================================================================
# DataIOFeature — UnifiedFeatureExtension
# ==============================================================================

class DataIOFeature(UnifiedFeatureExtension):
    """Unified extension for the Data I/O domain."""

    # ── Configuration (class attributes) ───────────────────────────────────

    domain_id = "data_io"
    actions = []
    section_title = "Export/Import Weight JSON"
    draw_tab = "LAYER"
    defaults_path = _DEFAULTS_PATH

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        return {"status": "CANCELLED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Draw the full Data I/O section: export/import buttons + settings."""
        wm = context.window_manager
        prefs = getattr(wm, "superskin_data_io_prefs", None)

        box = layout.box()
        box.label(text="Weight JSON Operations", icon='FILE_TICK')

        row = box.row(align=True)
        row.scale_y = 1.3
        row.operator("superskin.export_weight_json", text="Export JSON", icon='EXPORT')
        row.operator("superskin.import_weight_json", text="Import JSON", icon='IMPORT')

        if prefs:
            box_settings = layout.box()
            box_settings.label(text="IO Settings", icon='PROPERTIES')

            col = box_settings.column(align=True)
            col.prop(prefs, "export_precision")
            col.prop(prefs, "clear_unmapped_bones")

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """Write section data dict into the live WindowManager property."""
        wm = bpy.context.window_manager
        prefs = getattr(wm, "superskin_data_io_prefs", None)
        if prefs and "data_io" in data:
            io_data = data["data_io"]
            prefs.export_precision = io_data.get("export_precision", 5)
            prefs.clear_unmapped_bones = io_data.get("clear_unmapped_bones", False)

    def serialize_into(self, full_dict: dict) -> None:
        """Write current values into full_dict at the correct JSON path."""
        wm = bpy.context.window_manager
        prefs = getattr(wm, "superskin_data_io_prefs", None)
        if prefs:
            full_dict["data_io"] = {
                "export_precision": prefs.export_precision,
                "clear_unmapped_bones": prefs.clear_unmapped_bones,
            }


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register PropertyGroups on WindowManager and the extension with UnifiedRegistry."""
    bpy.utils.register_class(SSPrefWeightIO)
    bpy.types.WindowManager.superskin_data_io_prefs = bpy.props.PointerProperty(
        type=SSPrefWeightIO, options={'SKIP_SAVE'},
    )
    UnifiedRegistry.register(DataIOFeature())


def unregister():
    """Unregister PropertyGroups and the extension."""
    UnifiedRegistry.unregister("data_io")
    try:
        del bpy.types.WindowManager.superskin_data_io_prefs
    except Exception:
        pass
    bpy.utils.unregister_class(SSPrefWeightIO)
