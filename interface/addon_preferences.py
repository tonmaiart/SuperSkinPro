"""Blender native Add-on Preferences panel for SuperSkinPro.

Hosts System/Customize settings — color ramps, multi-color palette, license
activation, debug tools, and about — which were formerly in the SYSTEM tab
of the N-panel sidebar. Moving them here keeps the sidebar focused on
weight-painting operations and surfaces these settings in the standard
Blender location (Edit > Preferences > Add-ons > Super Skin Pro).
"""

import bpy

from . import widget_preferences
from .. import ADDON_PACKAGE


class SSP_AddonPreferences(bpy.types.AddonPreferences):
    # Must match the addon's actual runtime module name for Blender to locate
    # this class's instance in context.preferences.addons[...]. Blender
    # Extensions assign a repository-namespaced package name at install time
    # (e.g. "bl_ext.user_default.superskinpro"), not the manifest "id" or
    # folder name -- a hardcoded string here silently breaks the whole
    # preferences panel (no error, it just never shows). See __init__.py.
    bl_idname = ADDON_PACKAGE

    def draw(self, context):
        widget_preferences.draw_system_for_addon_prefs(self.layout, context)


def register():
    bpy.utils.register_class(SSP_AddonPreferences)


def unregister():
    bpy.utils.unregister_class(SSP_AddonPreferences)
