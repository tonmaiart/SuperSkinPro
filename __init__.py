"""Super Skin Pro — Professional weight painting layers system.

Unified Component Architecture: feature domains extend UnifiedFeatureExtension
and register with UnifiedRegistry (action dispatch + UI layout + persistence).

ST_STRICT: core/ is never touched except core/facade.py (public API surface).

All Extra Domain packages live under features/ and are registered through
features/__init__.py.

The interface/ package consolidates all front-end assets (panel, widgets,
operators, registry, template components, and utilities) into a single
closed subsystem.
"""

from importlib import reload

# ==============================================================================
# FORCE RELOAD — bottom-up order: foundations → features → interface
# ==============================================================================

from . import core
from . import core_subsystems   # backend pillars — no bpy classes, no register()
from . import interface         # closed front-end subsystem (registry + UI + ops)
from . import features          # all Extra Domain packages
from . import addon_updater_ops

for mod in (addon_updater_ops, core_subsystems, core, interface, features):
    try:
        reload(mod)
    except Exception:
        pass

# After interface is reloaded, pull in its deferred leaf modules
# (utils, ops_preferences, widget_preferences, addon_preferences, panel_main)
# now that core_subsystems is available.
try:
    interface._ensure_deferred()
except Exception:
    pass

# ==============================================================================
# BUILD FAKE bl_info — the addon uses blender_manifest.toml (Blender 4.2+),
# but addon_updater expects a bl_info dict with a "version" tuple.
# ==============================================================================
import tomllib as _tomllib
from pathlib import Path as _Path

_manifest_path = _Path(__file__).parent / "blender_manifest.toml"
with open(_manifest_path, "rb") as _fh:
    _manifest = _tomllib.load(_fh)

def _parse_version(version_str: str):
    """Parse a semver-like version string (e.g. '1.2.3') into an int tuple."""
    return tuple(int(p) for p in version_str.split("."))

_fake_bl_info = {
    "version": _parse_version(_manifest.get("version", "1.0")),
}

# ==============================================================================
# REGISTRATION
# ==============================================================================

def register():
    try:
        unregister()
    except Exception:
        pass

    # Register the auto-update system first — so users can roll back even if
    # a future version has a broken register().
    addon_updater_ops.register(_fake_bl_info)

    core.register()
    features.register()
    # Register the universal action proxy operator (SUPERSKIN_OT_execute_action)
    interface.registry.register_operator()
    # Load preferences after both core PropertyGroups and all feature
    # PrefsExtension specs are registered, so every extension gets populated.
    from .core_subsystems.preferences.preferences_service import PreferencesService
    PreferencesService.load()
    # Interface operators and panels (ops_preferences, addon_preferences, panel_main)
    interface.register()


def unregister():
    try:
        addon_updater_ops.unregister()
    except Exception:
        pass

    for component in (interface, features, core):
        try:
            component.unregister()
        except Exception:
            pass
    try:
        interface.registry.unregister_operator()
    except Exception:
        pass
