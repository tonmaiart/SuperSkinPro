"""Action operators behind the SuperSkinPro Preferences tab (drawn inline in
the N-panel by ``ui/widget_preferences.py`` — see that module for the draw
code; this file holds only the buttons' operator logic).
"""

import bpy
from ..core_subsystems.preferences.preferences_service import PreferencesService
from ..core_subsystems.license import LicenseService


class SUPERSKIN_OT_reset_prefs(bpy.types.Operator):
    """Reset all preferences to factory defaults immediately."""
    bl_idname = "superskin.reset_prefs"
    bl_label = "Reset Preferences"
    bl_options = {'REGISTER'}

    def execute(self, context):
        PreferencesService.reset_to_default()
        from ..core.shaders.shader_manager import ShaderManager
        ShaderManager().invalidate_color_only()
        PreferencesService.save_to_user_file()
        return {'FINISHED'}


class SUPERSKIN_OT_add_ramp_stop(bpy.types.Operator):
    """Add a new stop to a color ramp."""
    bl_idname = "superskin.add_ramp_stop"
    bl_label = "Add Ramp Stop"
    bl_options = {'REGISTER'}

    ramp_id: bpy.props.StringProperty(
        name="Ramp",
        description="Which ramp to add to ('single' or 'mask')",
        default="single",
    )

    def execute(self, context):
        prefs = context.window_manager.superskin_prefs
        customize = prefs.customize

        ramp_group = customize.mask_ramp if self.ramp_id == "mask" else customize.single_ramp
        stops_coll = ramp_group.stops

        # Interpolate from existing stops for a sensible default
        existing = sorted(((s.position, tuple(s.color)) for s in stops_coll),
                          key=lambda t: t[0])
        if len(existing) >= 2:
            mid_i = len(existing) // 2
            p0, c0 = existing[mid_i - 1]
            p1, c1 = existing[mid_i]
            new_pos = (p0 + p1) / 2.0
            new_color = tuple((c0[k] + c1[k]) / 2.0 for k in range(3))
        else:
            new_pos, new_color = 0.5, (1.0, 1.0, 1.0)

        s = stops_coll.add()
        s.position = new_pos
        s.color = new_color
        ramp_group.active_index = len(stops_coll) - 1
        from ..core.shaders.shader_manager import ShaderManager
        ShaderManager().invalidate_color_only()
        PreferencesService.save_to_user_file()
        return {'FINISHED'}


class SUPERSKIN_OT_remove_ramp_stop(bpy.types.Operator):
    """Remove a stop from a color ramp at the given index."""
    bl_idname = "superskin.remove_ramp_stop"
    bl_label = "Remove Ramp Stop"
    bl_options = {'REGISTER'}

    ramp_id: bpy.props.StringProperty(
        name="Ramp",
        description="Which ramp to remove from ('single' or 'mask')",
        default="single",
    )
    index: bpy.props.IntProperty(
        name="Index",
        description="Index of the stop to remove",
        default=0,
        min=0,
    )

    def execute(self, context):
        prefs = context.window_manager.superskin_prefs
        customize = prefs.customize

        ramp_group = customize.mask_ramp if self.ramp_id == "mask" else customize.single_ramp
        stops_coll = ramp_group.stops

        if 0 <= self.index < len(stops_coll):
            stops_coll.remove(self.index)
        ramp_group.active_index = max(0, min(ramp_group.active_index, len(stops_coll) - 1))
        from ..core.shaders.shader_manager import ShaderManager
        ShaderManager().invalidate_color_only()
        PreferencesService.save_to_user_file()
        return {'FINISHED'}


class SUPERSKIN_OT_move_ramp_stop(bpy.types.Operator):
    """Move a ramp stop up or down in the list (does not auto-sort by position)."""
    bl_idname = "superskin.move_ramp_stop"
    bl_label = "Move Ramp Stop"
    bl_options = {'REGISTER'}

    ramp_id: bpy.props.StringProperty(default="single")
    index: bpy.props.IntProperty(default=0, min=0)
    direction: bpy.props.IntProperty(default=-1)  # -1 = up, +1 = down

    def execute(self, context):
        prefs = context.window_manager.superskin_prefs
        customize = prefs.customize
        stops_coll = (customize.mask_ramp.stops if self.ramp_id == "mask"
                      else customize.single_ramp.stops)

        new_index = self.index + self.direction
        if 0 <= new_index < len(stops_coll):
            stops_coll.move(self.index, new_index)

        from ..core.shaders.shader_manager import ShaderManager
        ShaderManager().invalidate_color_only()
        PreferencesService.save_to_user_file()
        return {'FINISHED'}


class SUPERSKIN_OT_activate_license(bpy.types.Operator):
    """Verify the entered license key against Gumroad and cache the result."""
    bl_idname = "superskin.activate_license"
    bl_label = "Activate License"
    bl_options = {'REGISTER'}

    def execute(self, context):
        prefs = context.window_manager.superskin_prefs
        key = prefs.license.license_key.strip()
        if not key:
            self.report({'WARNING'}, "Enter a license key first")
            return {'CANCELLED'}

        success, message = LicenseService.activate(key)
        self.report({'INFO'} if success else {'WARNING'}, message)
        return {'FINISHED'}


class SUPERSKIN_OT_reset_license_activation(bpy.types.Operator):
    """Clear license key, activation token, and status message — debug/testing only."""
    bl_idname = "superskin.reset_license_activation"
    bl_label = "Reset All Activate"
    bl_options = {'REGISTER'}

    def execute(self, context):
        PreferencesService.set_license_activation("", "", "")
        self.report({'INFO'}, "License activation data cleared")
        return {'FINISHED'}


_classes = [
    SUPERSKIN_OT_reset_prefs,
    SUPERSKIN_OT_add_ramp_stop,
    SUPERSKIN_OT_remove_ramp_stop,
    SUPERSKIN_OT_move_ramp_stop,
    SUPERSKIN_OT_activate_license,
    SUPERSKIN_OT_reset_license_activation,
]


def register():
    for cls in _classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
