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

from ...registry.unified_feature_api import UnifiedFeatureExtension, UnifiedRegistry
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
    actions = ["export_weight", "import_weight"]
    section_title = "Export/Import Weight JSON"
    draw_tab = "LAYER"
    defaults_path = _DEFAULTS_PATH

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        from .logic import WeightIOProcessor

        wm = context.window_manager
        prefs = getattr(wm, "superskin_data_io_prefs", None)
        filepath = wm.get("superskin_io_filepath", "")

        # If action is empty, read from window manager
        if not action:
            action = wm.get("superskin_io_action", "")

        if not filepath:
            return {"status": "CANCELLED"}

        if action == "export_weight":
            print(f"[Weight IO] Exporting weights to: {filepath}")

            layer_dict = core_facade.get_active_layer_dict()
            success = WeightIOProcessor.export_to_json(filepath, layer_dict)
            if success:
                core_facade.show_toast(f"Exported successfully: {os.path.basename(filepath)}")
                return {"status": "FINISHED"}
            core_facade.show_toast("Export failed")
            return {"status": "CANCELLED"}

        elif action == "import_weight":
            print(f"[Weight IO] Importing weights from: {filepath}")

            imported_dict = WeightIOProcessor.import_from_json(filepath)

            if imported_dict is None:
                core_facade.show_toast("Failed to import: Invalid format or file not found")
                return {"status": "CANCELLED"}

            clear_unmapped = getattr(prefs, "clear_unmapped_bones", False)

            if clear_unmapped:
                current_layer = core_facade.get_active_layer_dict()

                for v_idx, current_bones in current_layer.items():
                    imported_bones_dict = imported_dict.get(v_idx, {})
                    imported_bones = set(imported_bones_dict.keys())

                    if v_idx not in imported_dict:
                        imported_dict[v_idx] = {}
                    elif not imported_bones:
                        imported_dict[v_idx] = {}
                    else:
                        current_bones_set = set(current_bones.keys())
                        for bone in current_bones_set - imported_bones:
                            if v_idx in imported_dict and bone in imported_dict[v_idx]:
                                del imported_dict[v_idx][bone]

            core_facade.write_layer_dict(imported_dict)
            core_facade.finish()
            core_facade.show_toast(f"Imported successfully: {os.path.basename(filepath)}")
            return {"status": "FINISHED"}

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
    # Backward-compat: also register with legacy registries during migration
    _register_legacy()


def unregister():
    """Unregister PropertyGroups and the extension."""
    _unregister_legacy()
    UnifiedRegistry.unregister("data_io")
    try:
        del bpy.types.WindowManager.superskin_data_io_prefs
    except Exception:
        pass
    bpy.utils.unregister_class(SSPrefWeightIO)


def _register_legacy():
    """Register with legacy registries for backward compatibility during migration."""
    try:
        from ...registry import DomainRegistry, BaseDomain, PrefsExtensionRegistry, PrefsExtensionSpec

        # Legacy BaseDomain registration
        class _WeightIODomain(BaseDomain):
            def get_id(self): return "data_io"
            def get_actions(self): return DataIOFeature().get_actions()
            def execute(self, action, context, core_facade):
                return DataIOFeature().execute(action, context, core_facade)
        DomainRegistry.register(_WeightIODomain())

        # Legacy PrefsExtensionSpec registration
        PrefsExtensionRegistry.register(PrefsExtensionSpec(
            json_key="data_io",
            json_path=("data_io",),
            section_title="Export/Import Weight JSON",
            draw_tab='LAYER',
            draw_section_fn=lambda layout: DataIOFeature().draw_section(layout, bpy.context),
            populate_fn=DataIOFeature().populate,
            serialize_into_fn=DataIOFeature().serialize_into,
            defaults_path=_DEFAULTS_PATH,
        ))
    except Exception:
        pass


def _unregister_legacy():
    """Remove from legacy registries."""
    try:
        from ...registry import PrefsExtensionRegistry
        PrefsExtensionRegistry.unregister("data_io")
    except Exception:
        pass
