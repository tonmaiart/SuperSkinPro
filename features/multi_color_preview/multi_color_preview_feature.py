"""MultiColorPreviewFeature — Unified Component Architecture implementation for the
multi-color preview domain.

Collapses the old MultiColorPreviewDomain (action dispatch) and prefs.py
(PropertyGroup scaffold, no-op draw/persistence) into a single
UnifiedFeatureExtension subclass.

Owns:
  - SSPrefMultiColorPreview PropertyGroup (registered on WindowManager)
  - Action dispatch: "start_multi_color", "stop_multi_color", "toggle_multi_color"
  - UI layout: draw_section() (no-op)
  - JSON persistence: populate() / serialize_into() (no-ops)
"""

import bpy
import os

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade
from . import draw as _draw

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


# ==============================================================================
# Property Groups
# ==============================================================================

class SSPrefMultiColorPreview(bpy.types.PropertyGroup):
    """Preferences for the multi-color per-bone weight preview.

    Currently a placeholder — no configurable properties yet.
    """


# ==============================================================================
# MultiColorPreviewFeature — UnifiedFeatureExtension
# ==============================================================================

class MultiColorPreviewFeature(UnifiedFeatureExtension):
    """Unified extension for the Multi Color Preview domain."""

    # ── Configuration (class attributes) ───────────────────────────────────

    domain_id = "multi_color_preview"
    actions = ["start_multi_color", "stop_multi_color", "toggle_multi_color"]
    section_title = "Multi Color Preview"
    # No N-panel UI -- draw_section() is a no-op (this domain is purely the
    # Alt+3 hold gesture, no configurable properties). draw_tab="" keeps it
    # out of the PREFERENCE-tab loop entirely, matching circle_tool_adjust's
    # pattern for keymap-only domains, instead of rendering an empty
    # collapsible box with nothing in it.
    draw_tab = ""
    defaults_path = _DEFAULTS_PATH

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        try:
            if action == "toggle_multi_color":
                _draw.toggle()
                core_facade.invalidate_and_redraw()
            elif action == "start_multi_color":
                _draw.start()
                core_facade.invalidate_and_redraw()
            elif action == "stop_multi_color":
                _draw.stop()
                core_facade.invalidate_and_redraw()
            else:
                return {"status": "CANCELLED", "message": f"Unknown action: {action}"}
        except Exception as e:
            return {"status": "CANCELLED", "message": str(e)}
        return {"status": "FINISHED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """No-op: the multi_color_preview domain has no configurable preferences UI."""
        pass

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """No-op: no preferences to populate."""
        pass

    def serialize_into(self, full_dict: dict) -> None:
        """No-op: no preferences to serialize."""
        pass


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register PropertyGroup on WindowManager and the extension with UnifiedRegistry."""
    bpy.utils.register_class(SSPrefMultiColorPreview)
    bpy.types.WindowManager.superskin_multi_color_preview_prefs = bpy.props.PointerProperty(
        type=SSPrefMultiColorPreview, options={'SKIP_SAVE'},
    )
    UnifiedRegistry.register(MultiColorPreviewFeature())


def unregister():
    """Unregister PropertyGroup and the extension."""
    UnifiedRegistry.unregister("multi_color_preview")
    try:
        del bpy.types.WindowManager.superskin_multi_color_preview_prefs
    except Exception:
        pass
    bpy.utils.unregister_class(SSPrefMultiColorPreview)
