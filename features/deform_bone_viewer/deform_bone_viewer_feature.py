"""DeformBoneViewerFeature — Unified Component Architecture implementation for the deform_bone_viewer domain.

Collapses the old DeformBoneViewerDomain (action dispatch) and prefs.py (draw,
persistence) into a single UnifiedFeatureExtension subclass.

This is a non-collapsible viewer domain that renders the Deform Bone List at the
top of the SKINNING tab at full width.
"""

import os
import bpy

from ...interface.registry.register_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade
from . import ui


_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


# ==============================================================================
# DeformBoneViewerFeature — UnifiedFeatureExtension
# ==============================================================================

class DeformBoneViewerFeature(UnifiedFeatureExtension):
    """Non-collapsible viewer extension for the Deform Bone List in the SKINNING tab."""

    # ── Configuration (class attributes) ──────────────────────────────────

    domain_id = "deform_bone_viewer"
    actions = []
    section_title = "Deform Bones List"
    draw_tab = "SKINNING"
    collapsible = True
    priority = 0
    expanded_by_default = True
    
    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        return {"status": "CANCELLED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Render the Deform Bone List and save/exit operator inside a box container."""
        box = layout.box()
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            box.label(text="No mesh active", icon='ERROR')
            return
        ui.draw_influence_list_system(box, context, rows=8)
        box.separator(factor=0.4)
        row = box.row()
        row.scale_y = 1.4
        row.operator("superskin.save_weight_and_exit", icon='IMPORT')

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        pass

    def serialize_into(self, full_dict: dict) -> None:
        pass


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register the feature with UnifiedRegistry and legacy registries."""
    UnifiedRegistry.register(DeformBoneViewerFeature())
    _register_legacy()


def unregister():
    """Unregister the feature from UnifiedRegistry and legacy registries."""
    _unregister_legacy()
    UnifiedRegistry.unregister("deform_bone_viewer")


def _register_legacy():
    """Register with legacy DomainRegistry and PrefsExtensionSpec for backward compat."""
    try:
        from ...interface.registry import DomainRegistry, BaseDomain, PrefsExtensionRegistry, PrefsExtensionSpec

        # Legacy BaseDomain registration
        class _DeformBoneViewerDomain(BaseDomain):
            def get_id(self): return "deform_bone_viewer"
            def get_actions(self): return []
            def execute(self, action, context, core_facade):
                return {"status": "CANCELLED"}
        DomainRegistry.register(_DeformBoneViewerDomain())

        # Legacy PrefsExtensionSpec registration (collapsible=False)
        PrefsExtensionRegistry.register(PrefsExtensionSpec(
            json_key="deform_bone_viewer",
            json_path=("deform_bone_viewer",),
            section_title="Deform Bones List",
            draw_tab="SKINNING",
            draw_section_fn=lambda layout: DeformBoneViewerFeature().draw_section(layout, bpy.context),
            populate_fn=lambda data: None,
            serialize_into_fn=lambda full_dict: None,
            defaults_path=_DEFAULTS_PATH,
            collapsible=False,
        ))
    except Exception:
        pass


def _unregister_legacy():
    """Remove from legacy PrefsExtensionRegistry."""
    try:
        from ...interface.registry import PrefsExtensionRegistry
        PrefsExtensionRegistry.unregister("deform_bone_viewer")
    except Exception:
        pass
