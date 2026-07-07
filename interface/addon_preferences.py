"""Blender native Add-on Preferences panel for SuperSkinPro.

This class only exists because the vendored updater (``addon_updater_ops.py``)
reads ``auto_check_update``/``updater_interval_*`` directly off
``context.preferences.addons[ADDON_PACKAGE].preferences``, which requires a
registered ``AddonPreferences`` subclass with this ``bl_idname`` to exist.

It no longer draws user-facing settings — System/Customize settings (color
ramps, palette, PREFERENCE-tab feature extensions, debug tools, about) moved
to the "Preference" panel in the viewport N-panel sidebar
(``interface/panel_gate.py``), since the Add-on Preferences window was hard
to reach.
"""

import bpy

from .. import ADDON_PACKAGE


class SSP_AddonPreferences(bpy.types.AddonPreferences):
    # Must match the addon's actual runtime module name for Blender to locate
    # this class's instance in context.preferences.addons[...]. Blender
    # Extensions assign a repository-namespaced package name at install time
    # (e.g. "bl_ext.user_default.superskinpro"), not the manifest "id" or
    # folder name -- a hardcoded string here silently breaks the whole
    # preferences panel (no error, it just never shows). See __init__.py.
    bl_idname = ADDON_PACKAGE

    # addon_updater_ops.py (vendored blender-addon-updater) reads these five
    # properties directly off get_user_preferences(context) -- both from its
    # UI drawing (update_settings_ui / update_settings_ui_condensed) and from
    # its background/interval check calls (updater.set_check_interval(...)).
    # It does not define or register them itself; the consuming addon's own
    # AddonPreferences is required to. Without them, any code path that
    # draws the updater settings raises "property not found" instead of
    # silently no-oping.
    auto_check_update: bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=False,
    )
    updater_interval_months: bpy.props.IntProperty(
        name="Months", description="Number of months between update checks",
        default=0, min=0,
    )
    updater_interval_days: bpy.props.IntProperty(
        name="Days", description="Number of days between update checks",
        default=7, min=0, max=31,
    )
    updater_interval_hours: bpy.props.IntProperty(
        name="Hours", description="Number of hours between update checks",
        default=0, min=0, max=23,
    )
    updater_interval_minutes: bpy.props.IntProperty(
        name="Minutes", description="Number of minutes between update checks",
        default=0, min=0, max=59,
    )

    def draw(self, context):
        self.layout.label(
            text="Super Skin Pro settings have moved to the N-panel sidebar"
        )
        self.layout.label(text="(Super Skin Pro tab > Preference panel).")


def register():
    bpy.utils.register_class(SSP_AddonPreferences)


def unregister():
    bpy.utils.unregister_class(SSP_AddonPreferences)
