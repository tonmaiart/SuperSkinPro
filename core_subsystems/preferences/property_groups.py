"""PropertyGroup classes for SuperSkinPro core preferences.

Registered on ``bpy.types.WindowManager.superskin_prefs`` — not Scene,
because these values are per-machine, not saved with the .blend file.

Feature domains own their own PropertyGroups (see features/<domain>/prefs.py).
"""

import bpy

# Hoisted from update callbacks — converted from absolute 'SuperSkinPro.*'
# imports to relative imports for Blender Extensions Platform compatibility.
from ...core.shaders.shader_manager import ShaderManager

# PreferencesService is deliberately NOT hoisted (unlike ShaderManager above).
# This file is reloaded *before* preferences_service.py in this package's own
# __init__.py reload loop (`for mod in (io, property_groups,
# preferences_service): reload(mod)`), so a module-level `from
# .preferences_service import PreferencesService` here would bind to the
# pre-reload class, permanently disconnected from the one `load()` sets
# `_loading` on — silently breaking the load()/save_to_user_file() reentrancy
# guard for every update= callback in this file, letting a mid-populate save
# write a torn snapshot over another extension's already-correct data. See
# docs/bug-history for the mirror-keywords-persistence report this was
# diagnosed from. Importing inside each callback instead resolves the name
# at call time, after all reload cascades have finished.
#
# New, intentional one-way exception to sibling-subsystem isolation (alongside
# the ShaderManager exception already used in this file): `preferences` nests
# SSPrefDebug into SSPrefRoot.debug so the "Developer / Debug Tools" panel has
# a single PropertyGroup root to draw from, the same way license/customize
# settings are nested here rather than living as their own top-level
# WindowManager properties.
from ..debug_logging.property_groups import SSPrefDebug


def _on_license_field_changed(self, context):
    from .preferences_service import PreferencesService
    PreferencesService.save_to_user_file()


def _on_visual_pref_changed(self, context):
    ShaderManager().invalidate_color_only()
    from .preferences_service import PreferencesService
    PreferencesService.save_to_user_file()


class SSPrefRampStop(bpy.types.PropertyGroup):
    """A single stop in a color ramp: position (0-1) and RGB color."""
    position: bpy.props.FloatProperty(
        name="Position",
        min=0.0, max=1.0,
        default=0.0,
        update=_on_visual_pref_changed,
    )
    color: bpy.props.FloatVectorProperty(
        name="Color",
        subtype='COLOR',
        size=3,
        min=0.0, max=1.0,
        default=(0.0, 0.0, 0.0),
        update=_on_visual_pref_changed,
    )


class SSPrefSingleRamp(bpy.types.PropertyGroup):
    """The single-mode color ramp (customizable black→blue→cyan→green→yellow→red→white)."""
    stops: bpy.props.CollectionProperty(type=SSPrefRampStop)
    active_index: bpy.props.IntProperty(name="Active Stop", default=0)


class SSPrefMaskRamp(bpy.types.PropertyGroup):
    """The mask/layer color ramp (customizable black→white)."""
    stops: bpy.props.CollectionProperty(type=SSPrefRampStop)
    active_index: bpy.props.IntProperty(name="Active Stop", default=0)


class SSPrefMultiPalette(bpy.types.PropertyGroup):
    """Fixed 10-color palette for MULTI bone mode (no add/remove UI)."""
    colors: bpy.props.CollectionProperty(type=SSPrefRampStop)


class SSPrefCustomize(bpy.types.PropertyGroup):
    """Groups the core Customize sub-groups (ramps and palette).

    BonePicker and other feature-owned PropertyGroups live on WindowManager
    as separate PointerProperties (e.g. superskin_bone_picker_prefs).
    """
    single_ramp:   bpy.props.PointerProperty(type=SSPrefSingleRamp)
    mask_ramp:     bpy.props.PointerProperty(type=SSPrefMaskRamp)
    multi_palette: bpy.props.PointerProperty(type=SSPrefMultiPalette)


class SSPrefLicense(bpy.types.PropertyGroup):
    """Gumroad license key + cached activation token (per-machine, in user.json).

    ``activation_token`` is an HMAC signature computed by the Rust core
    (``rust_verify_gumroad_license``) — it is NOT a trusted boolean flag.
    ``LicenseService.is_pro()`` always re-derives and compares it via Rust
    rather than reading a stored True/False, so hand-editing this value (or
    user_prefs.json) can't unlock Pro features.
    """
    license_key: bpy.props.StringProperty(
        name="License Key",
        default="",
        update=_on_license_field_changed,
    )
    activation_token: bpy.props.StringProperty(
        name="Activation Token",
        default="",
        options={'HIDDEN'},
    )
    status_message: bpy.props.StringProperty(
        name="Status Message",
        default="",
    )


class SSPrefCustomizeUIState(bpy.types.PropertyGroup):
    """Ephemeral UI-only state — section collapse/expand. Never persisted to JSON."""
    single_ramp_expanded:   bpy.props.BoolProperty(default=True)
    multi_palette_expanded: bpy.props.BoolProperty(default=True)
    mask_ramp_expanded:     bpy.props.BoolProperty(default=True)
    apply_toolkit_expanded: bpy.props.BoolProperty(default=False)


class SSPrefRoot(bpy.types.PropertyGroup):
    """Root PropertyGroup bound to WindowManager.superskin_prefs."""
    customize: bpy.props.PointerProperty(type=SSPrefCustomize)
    ui_state:  bpy.props.PointerProperty(type=SSPrefCustomizeUIState)
    license:   bpy.props.PointerProperty(type=SSPrefLicense)
    debug:     bpy.props.PointerProperty(type=SSPrefDebug)


# ── Registration helpers ──

_classes = [
    SSPrefRampStop,
    SSPrefSingleRamp,
    SSPrefMaskRamp,
    SSPrefMultiPalette,
    SSPrefCustomize,
    SSPrefCustomizeUIState,
    SSPrefLicense,
    SSPrefDebug,
    SSPrefRoot,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    # SKIP_SAVE: WindowManager is itself saved inside every .blend file, so
    # without this flag Blender would serialize whatever this PointerProperty
    # held at save time into the file, and restore that (possibly blank, if
    # the file predates this property, or stale) state on every later load —
    # turning "per-machine" preferences into accidental per-file ones. The
    # live values are repopulated from user.json by a load_post handler
    # instead (see core/preferences/__init__.py) — never from the .blend file.
    bpy.types.WindowManager.superskin_prefs = bpy.props.PointerProperty(
        type=SSPrefRoot, options={'SKIP_SAVE'},
    )


def unregister():
    del bpy.types.WindowManager.superskin_prefs
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
