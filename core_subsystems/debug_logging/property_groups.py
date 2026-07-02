"""SSPrefDebug -- per-category debug logging toggles.

Consumed by core_subsystems/preferences/property_groups.py, which nests this
PropertyGroup into SSPrefRoot.debug. Registration (bpy.utils.register_class)
is owned by that module's register()/unregister(), not by this package, since
SSPrefDebug only ever exists as a nested field of SSPrefRoot.

Deliberately never wired into PreferencesService's JSON load/save cycle --
these toggles are ephemeral (reset to off on every Blender restart), the same
way SSPrefCustomizeUIState is ephemeral. There is no persisted "last used
debug categories" state.
"""

import bpy

from .debug_log_service import CATEGORIES


class SSPrefDebug(bpy.types.PropertyGroup):
    """One BoolProperty per debug-log category, all default False."""
    temp_vg: bpy.props.BoolProperty(
        name="Temp VG & Mode Transitions",
        description="Edit/Object Mode transitions, __ssp_* temp Vertex Group bake/restore",
        default=False,
    )
    core_pipeline: bpy.props.BoolProperty(
        name="Core Storage & Compositor",
        description="Layer/mask read-write, composite flattening, ss_layer_N / ss_mask_N I/O",
        default=False,
    )
    rust_ffi: bpy.props.BoolProperty(
        name="Rust FFI Gateway",
        description="Data crossing the Python-Rust FFI boundary",
        default=False,
    )
    viewport_viz: bpy.props.BoolProperty(
        name="GPU Visualizer & Shaders",
        description="Heatmap/HUD drawing, shader cache invalidation, deform generation bumps",
        default=False,
    )
    bone_id: bpy.props.BoolProperty(
        name="Bone Identity & Orphans",
        description="Bone lock/mapping resolution, orphan bone scanning and remapping",
        default=False,
    )
    feature_domains: bpy.props.BoolProperty(
        name="Feature Domains",
        description="Extra Domain execute() dispatch (weight_apply, mirror, clipboard, etc.)",
        default=False,
    )


assert set(SSPrefDebug.__annotations__.keys()) == set(CATEGORIES), (
    "SSPrefDebug fields must match DebugLogService.CATEGORIES exactly"
)
