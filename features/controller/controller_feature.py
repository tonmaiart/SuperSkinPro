"""ControllerFeature — Unified Component Architecture implementation for the controller domain.

Collapses the old ControllerDomain (action dispatch) into a single
UnifiedFeatureExtension subclass.

This is a structural-only domain with no draw_section content in the N-panel.
All runtime behaviour (scene-mode switching, pie menu, safe-shrink) is
registered directly from __init__.py via the ops_* sub-modules.
"""

import bpy

from ...registry.unified_feature_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade


# ==============================================================================
# ControllerFeature — UnifiedFeatureExtension
# ==============================================================================

class ControllerFeature(UnifiedFeatureExtension):
    """Structural extension for the Controller domain (scene-mode gate, pie menu, utilities)."""

    # ── Configuration (class attributes) ───────────────────────────────────

    domain_id = "controller"
    actions = []
    section_title = "Controller"
    draw_tab = "SKINNING"
    collapsible = True

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        return {"status": "CANCELLED"}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Structural-only domain — no N-panel UI content."""
        pass

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        pass

    def serialize_into(self, full_dict: dict) -> None:
        pass


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register the feature with UnifiedRegistry and legacy DomainRegistry."""
    UnifiedRegistry.register(ControllerFeature())
    _register_legacy()


def unregister():
    """Unregister the feature from UnifiedRegistry."""
    # No PrefsExtensionSpec to unregister for this domain
    UnifiedRegistry.unregister("controller")


def _register_legacy():
    """Register with legacy DomainRegistry for backward compat during migration."""
    try:
        from ...registry import DomainRegistry, BaseDomain

        # Legacy BaseDomain registration
        class _ControllerDomain(BaseDomain):
            def get_id(self): return "controller"
            def get_actions(self): return []
            def execute(self, action, context, core_facade):
                return {"status": "CANCELLED"}
        DomainRegistry.register(_ControllerDomain())
    except Exception:
        pass
