"""WeightTransferFeature — Unified Component Architecture for Maya-style weight transfer.

Collapses the old WeightTransferDomain (action dispatch) and inline PrefsExtensionSpec
into a single UnifiedFeatureExtension subclass.

Owns:
  - Action dispatch: "transfer_weight_maya"
  - UI layout: delegates to .ui.draw_section()
  - JSON persistence: no-op (this domain has no user-editable prefs)
"""

import bpy
import os

from ...registry.unified_feature_api import UnifiedFeatureExtension, UnifiedRegistry
from ...core.facade import CoreFacade
from . import ui

_DEFAULTS_PATH = os.path.join(os.path.dirname(__file__), "default_config.json")


# ==============================================================================
# WeightTransferFeature — UnifiedFeatureExtension
# ==============================================================================

class WeightTransferFeature(UnifiedFeatureExtension):
    """Unified extension for the Weight Transfer domain."""

    # ── Configuration (class attributes) ───────────────────────────────────

    domain_id = "weight_transfer"
    actions = ["transfer_weight_maya"]
    section_title = "Toolkit"
    draw_tab = "LAYER"
    defaults_path = _DEFAULTS_PATH

    # ── Action dispatch ───────────────────────────────────────────────────

    def execute(self, action: str, context, core_facade: CoreFacade) -> dict:
        try:
            result = bpy.ops.object.mw_copy_skin_weight_maya()
            return {"status": "FINISHED" if 'FINISHED' in result else "CANCELLED"}
        except Exception as e:
            return {"status": "CANCELLED", "message": str(e)}

    # ── UI layout ─────────────────────────────────────────────────────────

    def draw_section(self, layout, context) -> None:
        """Draw the Toolkit section — delegates to .ui.draw_section()."""
        ui.draw_section(layout)

    # ── JSON persistence ──────────────────────────────────────────────────

    def populate(self, data: dict) -> None:
        pass

    def serialize_into(self, full_dict: dict) -> None:
        pass


# ==============================================================================
# Registration (called from __init__.py)
# ==============================================================================

def register():
    """Register with UnifiedRegistry and legacy registries for backward compat."""
    UnifiedRegistry.register(WeightTransferFeature())
    _register_legacy()


def unregister():
    """Unregister from all registries."""
    _unregister_legacy()
    UnifiedRegistry.unregister("weight_transfer")


def _register_legacy():
    """Register with legacy registries for backward compatibility during migration."""
    try:
        from ...registry import DomainRegistry, BaseDomain, PrefsExtensionRegistry, PrefsExtensionSpec

        # Legacy BaseDomain registration
        class _WeightTransferDomain(BaseDomain):
            def get_id(self): return "weight_transfer"
            def get_actions(self): return ["transfer_weight_maya"]
            def execute(self, action, context, core_facade):
                return WeightTransferFeature().execute(action, context, core_facade)
        DomainRegistry.register(_WeightTransferDomain())

        # Legacy PrefsExtensionSpec registration
        PrefsExtensionRegistry.register(PrefsExtensionSpec(
            json_key="weight_transfer",
            json_path=("weight_transfer",),
            section_title="Toolkit",
            draw_tab='LAYER',
            draw_section_fn=ui.draw_section,
            populate_fn=lambda data: None,
            serialize_into_fn=lambda d: None,
            defaults_path=_DEFAULTS_PATH,
        ))
    except Exception:
        pass


def _unregister_legacy():
    """Remove from legacy registries."""
    try:
        from ...registry import PrefsExtensionRegistry
        PrefsExtensionRegistry.unregister("weight_transfer")
    except Exception:
        pass
