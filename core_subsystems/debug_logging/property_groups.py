"""SSPrefDebug -- per-category debug logging toggles.

Consumed by core_subsystems/preferences/property_groups.py, which nests this
PropertyGroup into SSPrefRoot.debug. Registration (bpy.utils.register_class)
is owned by that module's register()/unregister(), not by this package, since
SSPrefDebug only ever exists as a nested field of SSPrefRoot.

Wired into PreferencesService's JSON load/save cycle (a "debug" section next
to "customize"/"license" in user.json — see preferences_service.py's
_populate_from_dict()/_dict_from_property_group()) so a category left
enabled survives a restart, the same way license/customize settings do.
"""

import bpy

from .debug_log_service import CATEGORIES


def _on_debug_changed(self, context):
    # Function-scoped: see core_subsystems/preferences/__init__.py's module
    # docstring for why PreferencesService must never be hoisted in a file
    # that's reloaded before preferences_service.py in the same cascade.
    from ..preferences.preferences_service import PreferencesService
    PreferencesService.save_to_user_file()


class SSPrefDebug(bpy.types.PropertyGroup):
    """One BoolProperty per debug-log category, all default False."""
    temp_vg: bpy.props.BoolProperty(
        name="Temp VG & Mode Transitions",
        description="Edit/Object Mode transitions, __ssp_* temp Vertex Group bake/restore",
        default=False,
        update=_on_debug_changed,
    )
    core_pipeline: bpy.props.BoolProperty(
        name="Core Storage & Compositor",
        description="Layer/mask read-write, composite flattening, ss_layer_N / ss_mask_N I/O",
        default=False,
        update=_on_debug_changed,
    )
    rust_ffi: bpy.props.BoolProperty(
        name="Rust FFI Gateway",
        description="Data crossing the Python-Rust FFI boundary",
        default=False,
        update=_on_debug_changed,
    )
    viewport_viz: bpy.props.BoolProperty(
        name="GPU Visualizer & Shaders",
        description="Heatmap/HUD drawing, shader cache invalidation, deform generation bumps",
        default=False,
        update=_on_debug_changed,
    )
    bone_id: bpy.props.BoolProperty(
        name="Bone Identity & Orphans",
        description="Bone lock/mapping resolution, orphan bone scanning and remapping",
        default=False,
        update=_on_debug_changed,
    )
    feature_domains: bpy.props.BoolProperty(
        name="Feature Domains",
        description="Extra Domain execute() dispatch (weight_apply, mirror, clipboard, etc.)",
        default=False,
        update=_on_debug_changed,
    )


assert set(SSPrefDebug.__annotations__.keys()) == set(CATEGORIES), (
    "SSPrefDebug fields must match DebugLogService.CATEGORIES exactly"
)
