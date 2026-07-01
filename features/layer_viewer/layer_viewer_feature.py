"""LayerViewerFeature — Unified Component Architecture implementation for the layer_viewer domain.

Collapses the old LayerViewerDomain (action dispatch) and prefs.py (draw,
persistence) into a single UnifiedFeatureExtension subclass.

This is a non-collapsible viewer domain that renders the Layer List at the
top of the LAYER tab at full width.
"""

import os
import bpy

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade
from . import ui


_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


# ==============================================================================
# LayerViewerFeature — UnifiedFeatureExtension
# ==============================================================================

class LayerViewerFeature(UnifiedFeatureExtension):
    """Non-collapsible viewer extension for the Layer List in the LAYER tab."""

    # ── Configuration (class attributes) ──────────────────────────────────

    domain_id = "layer_viewer"
    actions = []
    section_title = "Layers Management"
    draw_tab = "LAYER"
    collapsible = True
    priority = 0
    expanded_by_default = True
    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        return {"status": "CANCELLED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Render the Layer List and entry-gate operator inside a box container."""
        box = layout.box()
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            box.label(text="No mesh active", icon='ERROR')
            return
        if "ss_layers_meta" not in obj.data:
            box.label(text="Enter Edit Mode to initialize layers", icon='INFO')
            return
        ui.draw_layer_list(box, context, rows=8)
        box.separator(factor=0.4)
        row = box.row()
        row.scale_y = 1.4
        row.operator("superskin.enter_layer_edit", icon='EDITMODE_HLT')

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        pass

    def serialize_into(self, full_dict: dict) -> None:
        pass


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register the feature with UnifiedRegistry."""
    UnifiedRegistry.register(LayerViewerFeature())


def unregister():
    """Unregister the feature from UnifiedRegistry."""
    UnifiedRegistry.unregister("layer_viewer")
