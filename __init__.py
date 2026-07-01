"""Super Skin Pro — Professional weight painting layers system.

Unified Component Architecture: feature domains extend UnifiedFeatureExtension
and register with UnifiedRegistry (action dispatch + UI layout + persistence).

ST_STRICT: core/ is never touched except core/facade.py (public API surface).

All Extra Domain packages live under features/ and are registered through
features/__init__.py.
"""

bl_info = {
    "name": "Super Skin Pro",
    "author": "Natchapon Srisuk",
    "version": (1, 0),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Super Skin Pro",
    "description": "Professional weight painting layers system",
    "category": "Rigging",
}

from importlib import reload

# ==============================================================================
# FORCE RELOAD — bottom-up order: foundations → features → operators → UI
# ==============================================================================

from . import core
from . import core_subsystems   # backend pillars — no bpy classes, no register()
from . import registry          # DomainRegistry — no bpy classes, no register()
from . import shared
from . import features          # all Extra Domain packages
from . import operators
from . import ui

for mod in (core_subsystems, core, registry, shared, features, operators, ui):
    try:
        reload(mod)
    except Exception:
        pass

# ==============================================================================
# REGISTRATION
# ==============================================================================

def register():
    try:
        unregister()
    except Exception:
        pass

    core.register()
    features.register()
    # Register the universal action proxy operator
    registry.register_operator()
    # Load preferences after both core PropertyGroups and all feature
    # PrefsExtension specs are registered, so every extension gets populated.
    from .core_subsystems.preferences.preferences_service import PreferencesService
    PreferencesService.load()
    operators.register()
    ui.register()


def unregister():
    for component in (ui, operators, features, core):
        try:
            component.unregister()
        except Exception:
            pass
    try:
        registry.unregister_operator()
    except Exception:
        pass
