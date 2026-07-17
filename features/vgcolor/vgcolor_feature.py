"""VGColorFeature — Unified Component Architecture implementation for the
vgcolor domain.

Replaces the old "Single Mode Color Ramp" preference section. That section
used to edit this addon's own custom color-ramp PropertyGroup
(`customize.single_ramp`), which fed SuperSkinPro's own GPU draw shader
(`core/shaders/shader_manager.py`) for weight visualization. Now that
weight-paint visualization goes through Blender's native "show_weight"
overlay instead of a custom shader, that custom ramp had nothing left to
feed and was pure dead configuration.

Blender's native weight-paint visualization *is* itself user-adjustable,
through a real, built-in (non-addon) preference:

  - `bpy.context.preferences.view.use_weight_color_range` (bool) --
    "Enable color range used for weight visualization in weight painting
    mode" (this is the same toggle behind Blender's own Preferences >
    Editing > "Custom Weight Paint Range").
  - `bpy.context.preferences.view.weight_color_range` (ColorRamp,
    read-only pointer, but its stops/elements are fully editable) --
    the actual gradient stops.

This domain only draws a thin wrapper around those two native properties
-- no new operators, no custom ramp data model, no shader involvement.
Note this is a genuine **Blender user preference** (stored in Blender's
own preferences, not this addon's `user.json`), so it is shared across
every Blender file/project on this machine, not per-scene or per-object.
"""

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade


# ==============================================================================
# VGColorFeature — UnifiedFeatureExtension
# ==============================================================================

class VGColorFeature(UnifiedFeatureExtension):
    """Unified extension wrapping Blender's native weight-paint color ramp."""

    # ── Configuration (class attributes) ──────────────────────────────────

    domain_id = "vgcolor"
    actions = []
    section_title = "Weight Paint Color (VGColor)"
    draw_tab = "PREFERENCE"

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        return {"status": "CANCELLED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Toggle + native ColorRamp editor for
        `context.preferences.view.weight_color_range`."""
        view_prefs = context.preferences.view

        layout.prop(view_prefs, "use_weight_color_range", text="Custom Weight Paint Range")

        col = layout.column()
        col.enabled = view_prefs.use_weight_color_range
        col.template_color_ramp(view_prefs, "weight_color_range", expand=True)

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        """No-op -- `weight_color_range` is a native Blender user preference,
        not addon-owned state, so there is nothing for this addon's own
        user.json to load here."""
        pass

    def serialize_into(self, full_dict: dict) -> None:
        """No-op, for the same reason as populate()."""
        pass


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register the feature with UnifiedRegistry."""
    UnifiedRegistry.register(VGColorFeature())


def unregister():
    """Unregister the feature from UnifiedRegistry."""
    UnifiedRegistry.unregister("vgcolor")
